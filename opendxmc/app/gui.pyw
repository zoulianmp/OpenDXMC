# -*- coding: utf-8 -*-
"""
Created on Mon Jul 27 11:42:37 2015

@author: erlean
"""
import sys
import os
from PyQt4 import QtGui, QtCore
from opendxmc.app.view import View, ViewController
from opendxmc.app.model import DatabaseInterface, ListView, ListModel, RunManager, Importer, ImportScalingEdit, PropertiesEditWidget, OrganDoseModel, OrganDoseView
import logging

logger = logging.getLogger('OpenDXMC')
logger.setLevel(10)
LOG_FORMAT = ("[%(asctime)s %(name)s %(levelname)s]  -  %(message)s  -  in method %(funcName)s line:"
    "%(lineno)d filename: %(filename)s")


class LogHandler(QtCore.QObject, logging.Handler):
    message = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        QtCore.QObject.__init__(self, parent)
        logging.Handler.__init__(self)

        self.setFormatter(logging.Formatter(LOG_FORMAT, '%H:%M'))
#        self.log_formater = logging.Formatter()

    def emit(self, log_record):
        self.message.emit(self.format(log_record) + os.linesep)


class LogWidget(QtGui.QTextEdit):
    closed = QtCore.pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    def closeEvent(self, event):
        self.closed.emit(False)
        super().closeEvent(event)

class ImportPushButton(QtGui.QPushButton):
    files_to_import = QtCore.pyqtSignal(list)
    def __init__(self, txt, parent=None):
        super().__init__(txt, parent)
        self.clicked.connect(self.request_files)

    @QtCore.pyqtSlot()
    def request_files(self):
        files = QtGui.QFileDialog.getOpenFileNames(self,
                                                   'Select Helmholtz Centrum phantoms to import',
                                                   '/',
                                                   'ZIP files (*.zip); Raw text (*)')
        self.files_to_import.emit(files)




class StatusBarButton(QtGui.QPushButton):
    def __init__(self, *args):
        super().__init__(*args)
        self.setFlat(True)
        self.setCheckable(True)


class BusyWidget(QtGui.QWidget):
    def __init__(self, parent=None, tooltip=''):
        super().__init__(parent)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.progress)
        self.timer.timeout.connect(self.update)
        self.progress = 0
        self.pen = QtGui.QPen(QtGui.QBrush(QtCore.Qt.white), 50.,
                              cap=QtCore.Qt.RoundCap)
        self.setLayout(QtGui.QHBoxLayout())
        label = QtGui.QLabel('!')
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setToolTip(tooltip)
        self.setToolTip(tooltip)
        self.layout().addWidget(label)
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.setMinimumSize(QtGui.qApp.fontMetrics().size(QtCore.Qt.TextSingleLine, 'OpenDXMC'))

        self.setVisible(False)

    @QtCore.pyqtSlot()
    def progress(self):
        self.progress = (self.progress + 64) % 5760

    @QtCore.pyqtSlot(bool)
    def busy(self, start):
        self.setMinimumSize(QtGui.qApp.fontMetrics().size(QtCore.Qt.TextSingleLine, '!!!')*2)
        if start and not self.isVisible():
            self.timer.start(50)
            self.show()
        elif not start:
            self.hide()
            self.timer.stop()

    def paintEvent(self, ev):
        if self.width() > self.height():
            d = self.height()
        else:
            d = self.width()

        rect = QtCore.QRectF(0, 0, d*.70, d*.70)
        rect.moveCenter(QtCore.QPointF(self.rect().center()))

        self.pen.setWidthF(d * .15)
        p = QtGui.QPainter(self)
        p.setRenderHint(p.Antialiasing, True)

        self.pen.setColor(QtGui.QColor.fromHsv((self.progress // 16) % 180 + 0,
                                               255, 255))
        p.setPen(self.pen)
        p.drawArc(rect, self.progress, 960)
        self.pen.setColor(QtGui.QColor.fromHsv((self.progress // 16) % 180 + 180,
                                               255, 255))
        p.setPen(self.pen)
        p.drawArc(rect, self.progress + 2880, 960)


class MainWindow(QtGui.QMainWindow):
    def __init__(self):
        super().__init__()

        database_busywidget = BusyWidget(tooltip='Writing or Reading to Database')
        simulation_busywidget = BusyWidget(tooltip='Monte Carlo simulation in progress')
        importer_busywidget = BusyWidget(tooltip='Importing DICOM files')
        importer_phantoms_busywidget = BusyWidget(tooltip='Importing digital phantoms')

        # statusbar
        status_bar = QtGui.QStatusBar()
        statusbar_log_button = StatusBarButton('Log', None)
        status_bar.addPermanentWidget(importer_busywidget)
        status_bar.addPermanentWidget(importer_phantoms_busywidget)
        status_bar.addPermanentWidget(simulation_busywidget)
        status_bar.addPermanentWidget(database_busywidget)
        status_bar.addPermanentWidget(statusbar_log_button)

        self.setStatusBar(status_bar)

        # logging
        self.log_widget = LogWidget()
        self.log_handler = LogHandler(self)
        self.log_handler.message.connect(self.log_widget.insertPlainText)
        self.log_widget.closed.connect(statusbar_log_button.setChecked)
        statusbar_log_button.toggled.connect(self.log_widget.setVisible)
        logger.addHandler(self.log_handler)

        # central widget setup
        central_widget = QtGui.QWidget()
        central_widget.setContentsMargins(0, 0, 0, 0)
        self.setContentsMargins(0, 0, 0, 0)
        central_layout = QtGui.QHBoxLayout()
        central_splitter = QtGui.QSplitter(central_widget)
        central_layout.addWidget(central_splitter)
        central_layout.setContentsMargins(0, 0, 0, 0)




        # Databse interface
#        self.interface = DatabaseInterface(QtCore.QUrl.fromLocalFile('C:/Users/ander/Documents/GitHub/test.h5'))
        self.interface = DatabaseInterface(QtCore.QUrl.fromLocalFile('C:/test/test.h5'))
        self.interface.database_busy.connect(database_busywidget.busy)

        # importer
        self.importer = Importer(self.interface)
        self.importer.running.connect(importer_busywidget.busy)
        self.importer_phantom = Importer(self.interface)
        self.importer_phantom.running.connect(importer_phantoms_busywidget.busy)

        ## import scaling setter
        import_scaling_widget = ImportScalingEdit(self.importer, self)

        import_phantoms_button = ImportPushButton('Import Phantoms', self)
        import_phantoms_button.files_to_import.connect(self.importer.import_phantoms)


#        self.properties_model = PropertiesEditModel(self.interface)


        self.viewcontroller = ViewController(self.interface)


        ## MC runner
        self.mcrunner = RunManager(self.interface)
        self.mcrunner.mc_calculation_running.connect(simulation_busywidget.busy)
        self.viewcontroller.set_mc_runner(self.mcrunner.runner)


        # Models
        self.simulation_list_model = ListModel(self.interface, self.importer, self.importer_phantom, self,
                                               simulations=True)
        simulation_list_view = ListView()
        simulation_list_view.setModel(self.simulation_list_model)
        self.simulation_list_model.request_viewing.connect(self.viewcontroller.set_simulation)



        self.material_list_model = ListModel(self.interface, self,
                                             materials=True)
        material_list_view = ListView()
        material_list_view.setModel(self.material_list_model)

        # Widgets

        list_view_collection_widget = QtGui.QWidget()
        list_view_collection_widget.setContentsMargins(0, 0, 0, 0)
        list_view_collection_widget.setLayout(QtGui.QVBoxLayout())
        list_view_collection_widget.layout().setContentsMargins(0, 0, 0, 0)
        list_view_collection_widget.layout().addWidget(import_scaling_widget, 1)
        list_view_collection_widget.layout().addWidget(import_phantoms_button, 1)
        list_view_collection_widget.layout().addWidget(simulation_list_view, 3)
        list_view_collection_widget.layout().addWidget(material_list_view, 1)
        central_splitter.addWidget(list_view_collection_widget)

        simulation_editor = PropertiesEditWidget(self.interface, self.simulation_list_model, self.mcrunner)
        self.viewcontroller.set_simulation_editor(simulation_editor.model)
        central_splitter.addWidget(simulation_editor)


        central_splitter.addWidget(self.viewcontroller.view_widget())

        self.organdosemodel = OrganDoseModel(self.interface, self.simulation_list_model)
        organdoseview = OrganDoseView(self.organdosemodel)
        central_splitter.addWidget(organdoseview)


        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)

        # threading
        self.database_thread = QtCore.QThread(self)
        self.interface.moveToThread(self.database_thread)

        self.mc_thread = QtCore.QThread(self)
        self.mcrunner.moveToThread(self.mc_thread)

        self.dose_thread = QtCore.QThread(self)
#        self.organdosemodel.moveToThread(self.dose_thread)

        self.import_thread = QtCore.QThread(self)
        self.importer.moveToThread(self.import_thread)
        self.import_phantom_thread = QtCore.QThread(self)
        self.importer_phantom.moveToThread(self.import_phantom_thread)
#        self.importer.moveToThread(self.database_thread)

        self.import_thread.start()
        self.import_phantom_thread.start()
        self.mc_thread.start()
        self.dose_thread.start()
        self.database_thread.start()

        self.mcrunner.runner.finished.emit()


def main(args):

    app = QtGui.QApplication(args)
    app.setOrganizationName("SSHF")
#    app.setOrganizationDomain("https://code.google.com/p/ctqa-cp/")
    app.setApplicationName("OpenDXMC")
    win = MainWindow()
    win.show()

    return app.exec_()



def start():
    # exit code 1 triggers a restart
    # Also testing for memory error
    try:
        while main(sys.argv) == 1:
            continue
    except MemoryError:
        msg = QtGui.QMessageBox()
        msg.setText("Ouch, OpenDXMC ran out of memory.")
        msg.setIcon(msg.Critical)
        msg.exec_()
    sys.exit(0)


if __name__ == "__main__":
    pass
