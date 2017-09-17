import logging
from PyQt5.QtWidgets import QComboBox, QHeaderView, QLabel, QPushButton, QTableView, QTextEdit, QHBoxLayout, QVBoxLayout, QWidget
from PyQt5.QtGui import QPalette, QStandardItem, QStandardItemModel
from PyQt5.QtCore import Qt, pyqtSignal

from dbclient import sort_types

# small helper functions
def makeMediaInfo(info):
  if all(key in info for key in ["name", "track_count", "playlist_count", "bytes_total", "bytes_free"]):
    return "{}, {} tracks, {} playlists, {}/{}MB free".format(info["name"], info["track_count"],
      info["playlist_count"], info["bytes_free"]//1024//1024, info["bytes_total"]//1024//1024)
  else:
    return "No information available"

def makeItem(text, data=None):
  item = QStandardItem(text)
  item.setFlags(Qt.ItemIsEnabled)
  item.setData(data)
  return item

class Browser(QWidget):
  handleRequestSignal = pyqtSignal()
  refreshMediaSignal = pyqtSignal(str)

  def __init__(self, prodj, player_number):
    super().__init__()
    self.prodj = prodj
    self.slot = None # set after selecting slot in media menu
    self.menu = "media"
    self.sort = "default"
    self.artist_id = None
    self.track_id = None
    self.genre_id = None
    self.playlist_folder_id = None
    self.playlist_id = None
    self.setPlayerNumber(player_number)

    self.request = None # requests are parsed on signaling handleRequestSignal
    self.handleRequestSignal.connect(self.handleRequest)
    self.refreshMediaSignal.connect(self.refreshMedia)

    self.setAutoFillBackground(True)

    # upper part
    self.path = QLabel(self)
    self.sort_box = QComboBox(self)
    for sort in sort_types:
      self.sort_box.addItem(sort.title(), sort)
    self.sort_box.currentIndexChanged[int].connect(self.sortChanged)
    self.sort_box.setStyleSheet("QComboBox { padding: 2px; border-style: outset; border-radius: 2px; border-width: 1px; border-color: gray; }")
    self.back_button = QPushButton("Back", self)
    self.back_button.clicked.connect(self.backButtonClicked)
    self.back_button.setStyleSheet("QPushButton { padding: 2px; border-style: outset; border-radius: 2px; border-width: 1px; border-color: gray; }")

    top_layout = QHBoxLayout()
    top_layout.addWidget(self.path)
    top_layout.addWidget(self.sort_box)
    top_layout.addWidget(self.back_button)
    top_layout.setStretch(0, 1)

    # mid part
    self.model = QStandardItemModel(self)
    self.view = QTableView(self)
    self.view.setModel(self.model)
    self.view.verticalHeader().hide()
    #self.view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);
    self.view.verticalHeader().setSectionResizeMode(QHeaderView.Fixed);
    self.view.verticalHeader().setDefaultSectionSize(18); # TODO replace by text bounding height
    self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);
    self.view.setStyleSheet("QTableView { border-style: outset; border-radius: 2px; border-width: 1px; border-color: gray; background-color: black; } QTableView::item { color: white; } QTableView::item:focus { background-color: darkslategray; selection-background-color: black; }")
    self.view.clicked.connect(self.tableItemClicked)

    # metadata
    self.metadata_label = QLabel("Metadata:", self)
    self.metadata_edit = QTextEdit()
    self.metadata_edit.setReadOnly(True)
    self.metadata_edit.setStyleSheet("QTextEdit { padding: 2px; border-style: outset; border-radius: 2px; border-width: 1px; border-color: gray; }")

    metadata_layout = QVBoxLayout()
    metadata_layout.addWidget(self.metadata_label)
    metadata_layout.addWidget(self.metadata_edit)

    mid_layout = QHBoxLayout()
    mid_layout.addWidget(self.view)
    mid_layout.addLayout(metadata_layout)

    # lower part (load buttons)
    buttons_layout = QHBoxLayout()
    self.load_buttons = []
    for i in range(1,5):
      btn = QPushButton("Load Player {}".format(i), self)
      btn.setFlat(True)
      btn.setEnabled(False)
      btn.setStyleSheet("QPushButton { border-style: outset; border-radius: 2px; border-width: 1px; border-color: gray; }")
      btn.clicked.connect(lambda c,i=i: self.loadIntoPlayer(i))
      buttons_layout.addWidget(btn)
      self.load_buttons += [btn]

    layout = QVBoxLayout(self)
    layout.addLayout(top_layout)
    layout.addLayout(mid_layout)
    layout.addLayout(buttons_layout)

    self.updateButtons()
    self.mediaMenu()

  def setPlayerNumber(self, player_number):
    self.player_number = player_number
    self.setWindowTitle("Browse Player {}".format(player_number))

  def mediaMenu(self):
    c = self.prodj.cl.getClient(self.player_number)
    if c is None:
      logging.warning("Browser: failed to get client for player %d", self.player_number)
      return
    self.menu = "media"
    self.slot = None
    self.path.setText("Media overview")
    self.model.clear()
    if c.usb_state != "loaded" and c.sd_state != "loaded":
      self.model.setHorizontalHeaderLabels(["Media"])
      self.model.appendRow(makeItem("No media in player"))
      return
    self.model.setHorizontalHeaderLabels(["Media", "Info"])
    if c.usb_state == "loaded":
      data = {"type": "media", "name": "usb"}
      self.model.appendRow([makeItem("USB", data), makeItem(makeMediaInfo(c.usb_info), data)])
    if c.sd_state == "loaded":
      data = {"type": "media", "name": "sd"}
      self.model.appendRow([makeItem("SD Card", data), makeItem(makeMediaInfo(c.sd_info), data)])

  def rootMenu(self, slot):
    self.prodj.dbs.get_root_menu(self.player_number, slot, self.storeRequest)

  def renderRootMenu(self, request, player_number, slot, reply):
    logging.debug("renderRootMenu %s %s", str(request), str(player_number))
    if player_number != self.player_number:
      return
    self.menu = "root"
    self.slot = slot
    self.path.setText("Root menu "+slot)
    self.model.clear()
    self.model.setHorizontalHeaderLabels(["Category"])
    for entry in reply:
      data = {"type": "root", "name": entry["name"][1:-1], "menu_id": entry["menu_id"]}
      self.model.appendRow(makeItem(data["name"], data))
    #self.view.update()

  def titleMenu(self):
    self.prodj.dbs.get_titles(self.player_number, self.slot, self.sort, self.storeRequest)

  def artistMenu(self):
    self.prodj.dbs.get_artists(self.player_number, self.slot, self.sort, self.storeRequest)

  def albumArtistMenu(self, artist_id):
    self.artist_id = artist_id
    self.prodj.dbs.get_albums_by_artist(self.player_number, self.slot, artist_id, self.sort, self.storeRequest)

  def titleAlbumArtistMenu(self, album_id):
    self.prodj.dbs.get_titles_by_artist_album(self.player_number, self.slot, self.artist_id, album_id, self.sort, self.storeRequest)

  def albumMenu(self):
    self.prodj.dbs.get_albums(self.player_number, self.slot, self.sort, self.storeRequest)

  def titleAlbumMenu(self, album_id):
    self.prodj.dbs.get_titles_by_album(self.player_number, self.slot, album_id, self.sort, self.storeRequest)

  def genreMenu(self):
    self.prodj.dbs.get_genres(self.player_number, self.slot, self.storeRequest)

  def artistGenreMenu(self, genre_id):
    self.genre_id = genre_id
    self.prodj.dbs.get_artists_by_genre(self.player_number, self.slot, genre_id, self.storeRequest)

  def albumArtistGenreMenu(self, artist_id):
    self.artist_id = artist_id
    self.prodj.dbs.get_albums_by_genre_artist(self.player_number, self.slot, self.genre_id, artist_id, self.storeRequest)

  def titleAlbumArtistGenreMenu(self, album_id):
    self.album_id = album_id
    self.prodj.dbs.get_titles_by_genre_artist_album(self.player_number, self.slot, self.genre_id, self.artist_id, album_id, self.storeRequest)

  def playlistMenu(self, folder_id=0):
    self.playlist_folder_id = folder_id
    self.playlist_id = 0
    self.prodj.dbs.get_playlists(self.player_number, self.slot, folder_id, self.storeRequest)

  def titlePlaylistMenu(self, playlist_id=0):
    self.playlist_id = playlist_id
    self.prodj.dbs.get_playlist(self.player_number, self.slot, playlist_id, self.sort, self.storeRequest)

  def renderList(self, request, player_number, slot, query_ids, sort_mode, reply):
    logging.debug("renderList %s %s", request, str(player_number))
    if player_number != self.player_number:
      return
    self.menu = request
    self.slot = slot
    self.path.setText("{} on {}".format(request.title(), slot.upper()))
    self.model.clear()
    # guess columns
    columns = []
    if len(reply) > 0:
      for key in reply[0]:
        if key[-3:] != "_id":
          columns += [key]
    self.model.setHorizontalHeaderLabels([x.title() for x in columns])
    for entry in reply:
      entry_type = request
      if request == "playlist": # special playlist workarounds
        if "parent_id" in entry:
          self.playlist_folder_id = entry["parent_id"]
        if "track_id" in entry:
          entry_type = "title"
      data = {"type": entry_type, **entry}
      row = []
      for column in columns:
        row += [makeItem(str(entry[column]), data)]
      self.model.appendRow(row)

  def metadata(self, track_id):
    self.prodj.dbs.get_metadata(self.player_number, self.slot, track_id, self.storeRequest)

  def renderMetadata(self, request, source_player_number, slot, track_id, metadata):
    md = ""
    for key in [k for k in ["title", "artist", "album", "genre", "key", "bpm", "comment", "rating", "duration"] if k in metadata]:
      md += "{}:\t{}\n".format(key.title(), metadata[key])
    self.metadata_edit.setText(md)
    self.track_id = track_id

  def backButtonClicked(self):
    if self.menu in ["title", "artist", "album", "genre"]:
      self.rootMenu(self.slot)
    elif self.menu == "title_by_artist_album":
      self.albumArtistMenu(self.artist_id)
    elif self.menu == "title_by_album":
      self.albumMenu()
    elif self.menu == "album_by_artist":
      self.artistMenu()
    elif self.menu == "artist_by_genre":
      self.genreMenu()
    elif self.menu == "album_by_genre_artist":
      self.artistGenreMenu(self.genre_id)
    elif self.menu == "title_by_genre_artist_album":
      self.albumArtistGenreMenu(self.artist_id)
    elif self.menu == "playlist":
      if self.playlist_folder_id == 0 and self.playlist_id == 0:
        self.rootMenu(self.slot)
      else:
        self.playlistMenu(self.playlist_folder_id)
    elif self.menu == "root":
      self.mediaMenu()
    elif  self.menu == "media":
      pass # no parent menu for media
    else:
      logging.debug("Browser: back button for %s not implemented yet", self.menu)

  def tableItemClicked(self, index):
    data = self.model.itemFromIndex(index).data()
    logging.debug("Browser: clicked data %s", data)
    if data is None:
      return
    if data["type"] == "media":
      self.rootMenu(data["name"])
    elif data["type"] == "root":
      if data["name"] == "TRACK":
        self.titleMenu()
      elif data["name"] == "ARTIST":
        self.artistMenu()
      elif data["name"] == "ALBUM":
        self.albumMenu()
      elif data["name"] == "GENRE":
        self.genreMenu()
      elif data["name"] == "PLAYLIST":
        self.playlistMenu()
      else:
        logging.warning("Browser: root menu type %s not implemented yet", data["name"])
    elif data["type"] == "album":
      self.titleAlbumMenu(data["album_id"])
    elif data["type"] == "artist":
      self.albumArtistMenu(data["artist_id"])
    elif data["type"] == "album_by_artist":
      self.titleAlbumArtistMenu(data["album_id"])
    elif data["type"] == "genre":
      self.artistGenreMenu(data["genre_id"])
    elif data["type"] == "artist_by_genre":
      self.albumArtistGenreMenu(data["artist_id"])
    elif data["type"] == "album_by_genre_artist":
      self.titleAlbumArtistGenreMenu(data["album_id"])
    elif data["type"] == "folder":
      self.playlistMenu(data["folder_id"])
    elif data["type"] == "playlist":
      self.titlePlaylistMenu(data["playlist_id"])
    elif data["type"] in ["title", "title_by_album", "title_by_artist_album", "title_by_genre_artist_album"]:
      self.metadata(data["track_id"])
    else:
      logging.warning("Browser: unhandled click type %s", data["type"])
    self.updateButtons() # update buttons for convenience

  def sortChanged(self):
    self.sort = self.sort_box.currentData()
    if self.menu in ["title"]:
      logging.debug("sort changed to %s", self.sort)
      self.titleMenu()

  def loadIntoPlayer(self, player_number):
    if self.slot is None or self.track_id is None:
      return
    logging.debug("Browser: loading track (pn %d slot %s tid %d) into player %d",
      self.player_number, self.slot, self.track_id, player_number)
    self.prodj.vcdj.command_load_track(player_number, self.player_number, self.slot, self.track_id)

  def updateButtons(self):
    for i in range(1,5):
      self.load_buttons[i-1].setEnabled(self.prodj.cl.getClient(i) is not None)

  # special request handling to get into qt gui thread
  # storeRequest is called from outside (non-qt gui)
  def storeRequest(self, request, *args):
    if self.request is not None:
      logging.debug("Browser: not storing request %s, other request pending", request)
    logging.debug("Browser: storing request %s", request)
    self.request = (request, *args)
    self.handleRequestSignal.emit()

  # handleRequest is called by handleRequestSignal, from inside the gui thread
  def handleRequest(self):
    logging.debug("handleRequest %s", self.request[0])
    if self.request is None:
      return
    if self.request[0] == "root_menu":
      self.renderRootMenu(*self.request)
    elif self.request[0] in ["title", "artist", "album_by_artist", "title_by_artist_album", "album", "title_by_album", "genre", "artist_by_genre", "album_by_genre_artist", "title_by_genre_artist_album", "playlist"]:
      self.renderList(*self.request)
    elif self.request[0] == "metadata":
      self.renderMetadata(*self.request)
    else:
      logging.warning("Browser: %s request not implemented", self.request[0])
    self.request = None

  def refreshMedia(self, slot):
    if self.slot == slot or self.menu == "media":
      logging.info("Browser: slot %s changed, going back to media overview")
      self.mediaMenu()
    else:
      logging.debug("Browser: ignoring %s change", slot)