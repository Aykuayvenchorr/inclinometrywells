from math import sqrt

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QTimer, Qt
from qgis.PyQt.QtWidgets import QMessageBox

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
)

from qgis.gui import QgsMapToolIdentifyFeature
from qgis.utils import iface

from ..settings.TableColumns import TableColumns


IncCol = TableColumns.inclinometry


class TabTarget:
    """
    Логика вкладки Targets.

    Отвечает за:
    - выбор проектных целей на карте;
    - получение координат цели из геометрии или атрибутов;
    - преобразование координат между CRS;
    - работу с таблицей целей;
    - расчёт фактического положения цели по инклинометрии;
    - добавление фактической цели в слой welltarget.
    """

    # Индексы колонок tableTargets
    COL_ID = 0
    COL_STRATUM = 1
    COL_NAME = 2
    COL_NORTH = 3
    COL_EAST = 4
    COL_TVD = 5
    COL_TVDSS = 6
    COL_MD = 7
    COL_NORTH_FACT = 8
    COL_EAST_FACT = 9
    COL_R_FACT = 10
    COL_TVDSS_FACT = 11

    # Количество знаков после запятой
    GEOGRAPHIC_DECIMALS = 10
    PROJECTED_DECIMALS = 3

    # Соответствие проектного типа фактическому
    PROJECT_TO_FACT_TYPE = {
        0: 2,  # Кровля проект -> Кровля факт
        1: 3,  # Подошва проект -> Подошва факт
        4: 5,  # Проектная цель -> Проектная инклинометрия
    }

    def __init__(self, dialog):
        """
        Инициализация вкладки Targets.
        """

        self.tab = dialog

        # Слой целей
        self.layerTarget = None

        # CRS исходного слоя целей
        self.crsLayerTarget = None

        # CRS, выбранная пользователем
        self.crsOutputTarget = None

        # CRS, в которой сейчас находятся координаты таблицы
        self.crsTableTarget = None

        # CRS текущей добавляемой цели
        self.crsCurrentTarget = None

        # Инструмент выбора объекта на карте
        self.targetIdentifyTool = None

        self._connectSignals()
        self._initializeWidgets()

    # ==================================================================
    # ИНИЦИАЛИЗАЦИЯ
    # ==================================================================

    def _connectSignals(self):
        """Подключает сигналы элементов интерфейса."""

        self.tab.mQgsProjectionSelectionWidgetTarget.crsChanged.connect(
            self.targetCrsChanged
        )

        self.tab.btnRemoveTarget.clicked.connect(
            self.deleteTarget
        )

        self.tab.btnCalculateDeviations.clicked.connect(
            self.calculateDeviations
        )
        self.tab.btnAddTargetRow.clicked.connect(
            self.addEmptyTargetRow
        )
        self.tab.btnAddTarget.clicked.connect(
            self.addTargetsToLayer
        )

    def _initializeWidgets(self):
        """Начальная настройка элементов интерфейса."""

        self.tab.btnCalculateDeviations.setEnabled(False)

    # ==================================================================
    # СООБЩЕНИЯ
    # ==================================================================

    def showWarning(self, title, message):
        """Показывает предупреждение пользователю."""

        QMessageBox.warning(
            self.tab,
            title,
            message,
        )

    # ==================================================================
    # СПОСОБ ПОЛУЧЕНИЯ КООРДИНАТ
    # ==================================================================

    def getCoordinatesSource(self):
        """
        Возвращает способ получения координат.

        Returns:
            "map"   — координаты берутся из геометрии;
            "value" — координаты берутся из атрибутов;
            None    — способ не выбран.
        """

        if self.tab.tabTargetsCRSMapBtn.isChecked():
            return "map"

        if self.tab.tabTargetsCRSValueBtn.isChecked():
            return "value"

        self.showWarning(
            "Внимание",
            "Выберите способ получения координат.",
        )

        return None

    def checkCoordinateMethod(self):
        """
        Совместимый wrapper для старого кода.

        Использует getCoordinatesSource().
        """

        return self.getCoordinatesSource()

    # ==================================================================
    # ВЫБОР ЦЕЛИ НА КАРТЕ
    # ==================================================================

    def selectTarget(self):
        """
        Включает режим выбора целей на карте.
        """

        self.layerTarget = (
            self.tab.tabSettingsTargetsMLCBox.currentLayer()
        )

        if not self._validateTargetLayer():
            return

        self.crsLayerTarget = self.layerTarget.crs()

        if not self._validateLayerCrs():
            return

        self._initializeIdentifyTool()

        iface.mapCanvas().setMapTool(
            self.targetIdentifyTool
        )

    def _validateTargetLayer(self):
        """Проверяет выбранный слой целей."""

        if self.layerTarget is None:
            self.showWarning(
                "Внимание",
                "Сначала выберите слой целей.",
            )
            return False

        if not self.layerTarget.isValid():
            self.showWarning(
                "Внимание",
                "Выбранный слой целей недействителен.",
            )
            return False

        return True

    def _validateLayerCrs(self):
        """Проверяет CRS слоя целей."""

        if (
            self.crsLayerTarget is None
            or not self.crsLayerTarget.isValid()
        ):
            self.showWarning(
                "Ошибка",
                "Не определена система координат слоя целей.",
            )
            return False

        return True

    def _initializeIdentifyTool(self):
        """
        Создаёт инструмент выбора цели, если он ещё не создан.
        """

        if self.targetIdentifyTool is not None:
            self.targetIdentifyTool.setLayer(
                self.layerTarget
            )
            return

        self.targetIdentifyTool = QgsMapToolIdentifyFeature(
            iface.mapCanvas()
        )

        self.targetIdentifyTool.setLayer(
            self.layerTarget
        )

        self.targetIdentifyTool.featureIdentified.connect(
            self.targetSelected
        )

    # ==================================================================
    # ВЫБОР ОБЪЕКТА
    # ==================================================================

    def targetSelected(self, feature):
        """
        Обрабатывает выбранную цель.
        """

        self.addTargetToTable(feature)

        # Инструмент намеренно остаётся активным,
        # чтобы можно было выбрать следующую цель.

    # ==================================================================
    # ДОБАВЛЕНИЕ ЦЕЛИ В ТАБЛИЦУ
    # ==================================================================

    def addTargetToTable(self, feature):
        """
        Добавляет выбранную цель в tableTargets.

        Источник координат:
            map   — геометрия объекта;
            value — поля east/north + crs_text.
        """

        coordinates_source = self.getCoordinatesSource()

        if coordinates_source is None:
            return

        coordinates = self._getTargetCoordinates(
            feature,
            coordinates_source,
        )

        if coordinates is None:
            return

        east, north = coordinates

        # Если таблица уже содержит цели,
        # переводим существующие координаты
        # из старой CRS в текущую.
        if self.tab.tableTargets.rowCount() > 0:
            self.transformCoordinatesInTable()

        self._setTargetCrsWidget(
            self.crsCurrentTarget
        )

        self.pointAddToTable(
            QgsPointXY(east, north),
            feature,
        )

        self.crsTableTarget = self.crsCurrentTarget

        self._refreshTargetCrsWidget()

        self.tab.btnCalculateDeviations.setEnabled(True)

    def _getTargetCoordinates(self, feature, source):
        """
        Получает координаты выбранной цели.

        Returns:
            tuple[float, float] | None:
                east, north
        """

        if source == "map":
            return self._getCoordinatesFromGeometry(feature)

        if source == "value":
            return self._getCoordinatesFromAttributes(feature)

        return None

    def _getCoordinatesFromGeometry(self, feature):
        """Получает координаты из геометрии цели."""

        geometry = feature.geometry()

        if geometry is None or geometry.isEmpty():
            self.showWarning(
                "Ошибка",
                "У выбранной цели отсутствует геометрия.",
            )
            return None

        point = geometry.asPoint()

        self.crsCurrentTarget = self.crsLayerTarget

        return point.x(), point.y()

    def _getCoordinatesFromAttributes(self, feature):
        """Получает координаты и CRS из атрибутов цели."""

        east = feature["east"]
        north = feature["north"]

        if east is None or north is None:
            self.showWarning(
                "Ошибка",
                "В атрибутах выбранной цели отсутствуют "
                "координаты east/north.",
            )
            return None

        try:
            east = float(east)
            north = float(north)
        except (TypeError, ValueError):
            self.showWarning(
                "Ошибка",
                "Значения полей east и north должны быть числовыми.",
            )
            return None

        crs = self._getCrsFromFeature(feature)

        if crs is None:
            return None

        self.crsCurrentTarget = crs

        return east, north

    def _getCrsFromFeature(self, feature):
        """Получает CRS из поля crs_text."""

        crs_text = feature["crs_text"]

        if crs_text is None or not str(crs_text).strip():
            self.showWarning(
                "Ошибка",
                "В атрибутах выбранной цели не указана "
                "система координат в поле crs_text.",
            )
            return None

        crs_text = str(crs_text).strip()

        crs = QgsCoordinateReferenceSystem(
            crs_text
        )

        if not crs.isValid():
            self.showWarning(
                "Ошибка",
                f"Не удалось определить систему координат:\n{crs_text}",
            )
            return None

        return crs

    # ==================================================================
    # CRS ВИДЖЕТ
    # ==================================================================

    def _setTargetCrsWidget(self, crs):
        """Устанавливает CRS в виджет без вызова обработчика."""

        widget = (
            self.tab.mQgsProjectionSelectionWidgetTarget
        )

        widget.blockSignals(True)

        try:
            widget.setCrs(crs)
        finally:
            widget.blockSignals(False)

    def _refreshTargetCrsWidget(self):
        """Обновляет отображение CRS-виджета."""

        widget = (
            self.tab.mQgsProjectionSelectionWidgetTarget
        )

        QTimer.singleShot(
            0,
            widget.update,
        )

        QTimer.singleShot(
            0,
            widget.repaint,
        )

    # ==================================================================
    # ФОРМАТИРОВАНИЕ КООРДИНАТ
    # ==================================================================

    def formatTargetCoordinates(self, point):
        """
        Форматирует координаты в зависимости от CRS.
        """

        if self.crsCurrentTarget.isGeographic():
            decimals = self.GEOGRAPHIC_DECIMALS
        else:
            decimals = self.PROJECTED_DECIMALS

        north_text = f"{point.y():.{decimals}f}"
        east_text = f"{point.x():.{decimals}f}"

        return north_text, east_text

    # ==================================================================
    # ИЗМЕНЕНИЕ CRS
    # ==================================================================

    def targetCrsChanged(self, crs):
        """
        Обрабатывает изменение CRS пользователем.

        Уже добавленные координаты переводятся
        из предыдущей CRS в новую.
        """

        if crs is None or not crs.isValid():
            return

        if crs == self.crsCurrentTarget:
            return

        self.crsCurrentTarget = crs

        # Если таблица ещё не содержит координат,
        # преобразовывать нечего.
        if self.tab.tableTargets.rowCount() == 0:
            self.crsTableTarget = crs
            return

        self.transformCoordinatesInTable()

    def transformCoordinatesInTable(self):
        """
        Пересчитывает координаты всех целей в таблице
        из CRS таблицы в текущую CRS.
        """

        if (
            self.crsTableTarget is None
            or not self.crsTableTarget.isValid()
            or self.crsCurrentTarget is None
            or not self.crsCurrentTarget.isValid()
        ):
            return

        if self.crsTableTarget == self.crsCurrentTarget:
            return

        transform = QgsCoordinateTransform(
            self.crsTableTarget,
            self.crsCurrentTarget,
            QgsProject.instance(),
        )

        table = self.tab.tableTargets

        for row in range(table.rowCount()):
            coordinates = self._getTableCoordinates(row)

            if coordinates is None:
                continue

            north, east = coordinates

            try:
                target_point = transform.transform(
                    QgsPointXY(east, north)
                )
            except Exception as error:
                print(
                    f"Ошибка преобразования координат "
                    f"цели в строке {row}: {error}"
                )
                continue

            north_text, east_text = (
                self.formatTargetCoordinates(
                    target_point
                )
            )

            table.item(
                row,
                self.COL_NORTH,
            ).setText(north_text)

            table.item(
                row,
                self.COL_EAST,
            ).setText(east_text)

        self.crsTableTarget = self.crsCurrentTarget

    def _getTableCoordinates(self, row):
        """Получает north/east из строки таблицы."""

        table = self.tab.tableTargets

        north_item = table.item(
            row,
            self.COL_NORTH,
        )

        east_item = table.item(
            row,
            self.COL_EAST,
        )

        if north_item is None or east_item is None:
            return None

        try:
            north = float(
                north_item.text().replace(",", ".")
            )
            east = float(
                east_item.text().replace(",", ".")
            )
        except (TypeError, ValueError):
            return None

        return north, east

    # ==================================================================
    # ДОБАВЛЕНИЕ СТРОКИ В ТАБЛИЦУ
    # ==================================================================

    def pointAddToTable(self, point, feature):
        """
        Добавляет одну цель в tableTargets.
        """

        table = self.tab.tableTargets

        row = table.rowCount()
        table.insertRow(row)

        self._setTableItem(
            table,
            row,
            self.COL_ID,
            feature["id"],
        )

        self._setTableItem(
            table,
            row,
            self.COL_STRATUM,
            feature["stratum"],
        )

        self._setTableItem(
            table,
            row,
            self.COL_NAME,
            feature["name"],
        )

        north_text, east_text = (
            self.formatTargetCoordinates(point)
        )

        self._setTableItem(
            table,
            row,
            self.COL_NORTH,
            north_text,
        )

        self._setTableItem(
            table,
            row,
            self.COL_EAST,
            east_text,
        )

        self._setTableItem(
            table,
            row,
            self.COL_TVD,
            feature["tvd"],
        )

        self._setTableItem(
            table,
            row,
            self.COL_TVDSS,
            feature["tvdss"],
        )

    @staticmethod
    def _setTableItem(table, row, column, value):
        """Создаёт и устанавливает QTableWidgetItem."""

        text = "" if value is None else str(value)

        table.setItem(
            row,
            column,
            QtWidgets.QTableWidgetItem(text),
        )

    # ==================================================================
    # ОЧИСТКА / УДАЛЕНИЕ
    # ==================================================================

    def clearSelectedTarget(self):
        """
        Сбрасывает инструмент выбора цели.
        """

        if self.targetIdentifyTool is None:
            return

        iface.mapCanvas().unsetMapTool(
            self.targetIdentifyTool
        )

        self.targetIdentifyTool = None

    def deleteTarget(self):
        """
        Удаляет выбранную цель из tableTargets.
        """

        table = self.tab.tableTargets
        row = table.currentRow()

        if row < 0:
            self.showWarning(
                "Внимание",
                "Выберите цель в таблице для удаления.",
            )
            return

        table.removeRow(row)

        if table.rowCount() == 0:
            self.tab.btnCalculateDeviations.setEnabled(False)

            # После удаления последней цели
            # таблица координат больше не содержит данных.
            self.crsTableTarget = self.crsCurrentTarget

    # ==================================================================
    # РАСЧЁТ ОТКЛОНЕНИЙ
    # ==================================================================

    def calculateDeviations(self):
        """
        Рассчитывает фактическое положение всех целей
        по данным инклинометрии.
        """

        self._refreshTargetLayer()

        self._syncTargetCrsWithWellhead()

        table = self.tab.tableTargets

        for row in range(table.rowCount()):
            result = self.calculateCoordsTarget(row)

            if result is None:
                continue

            north_fact, east_fact, tvdss_fact = result

            self._writeCalculatedTargetValues(
                row,
                north_fact,
                east_fact,
                tvdss_fact,
            )

            north_target = self._getTableFloat(
                row,
                self.COL_NORTH,
            )

            east_target = self._getTableFloat(
                row,
                self.COL_EAST,
            )

            if north_target is None or east_target is None:
                continue

            deviation = self.calculateRfact(
                north_target,
                east_target,
                north_fact,
                east_fact,
            )

            self._setTableItem(
                table,
                row,
                self.COL_R_FACT,
                f"{deviation:.3f}",
            )

            self.addActualTargetToLayer(
                row,
                north_fact,
                east_fact,
                tvdss_fact,
            )

    def _refreshTargetLayer(self):
        """Обновляет слой целей перед расчётом."""

        layer = (
            self.tab.tabSettingsTargetsMLCBox.currentLayer()
        )

        if layer is None:
            return

        layer.updateFields()
        layer.updateExtents()
        layer.triggerRepaint()

    def _syncTargetCrsWithWellhead(self):
        """
        Синхронизирует CRS целей с CRS устья скважины.
        """

        target_widget = (
            self.tab.mQgsProjectionSelectionWidgetTarget
        )

        wellhead_widget = (
            self.tab.mQgsProjectionSelectionWidgetWellHead
        )

        target_crs = target_widget.crs()
        wellhead_crs = wellhead_widget.crs()

        if target_crs == wellhead_crs:
            return

        if wellhead_crs is None or not wellhead_crs.isValid():
            return

        target_widget.blockSignals(True)

        try:
            target_widget.setCrs(wellhead_crs)
            self.targetCrsChanged(
                target_widget.crs()
            )
        finally:
            target_widget.blockSignals(False)

        self.crsTableTarget = self.crsCurrentTarget

        self._refreshTargetCrsWidget()

    def _writeCalculatedTargetValues(
        self,
        row,
        north_fact,
        east_fact,
        tvdss_fact,
    ):
        """Записывает рассчитанные координаты фактической цели."""

        table = self.tab.tableTargets

        self._setTableItem(
            table,
            row,
            self.COL_NORTH_FACT,
            f"{north_fact:.3f}",
        )

        self._setTableItem(
            table,
            row,
            self.COL_EAST_FACT,
            f"{east_fact:.3f}",
        )

        self._setTableItem(
            table,
            row,
            self.COL_TVDSS_FACT,
            f"{tvdss_fact:.3f}",
        )

    def _getTableFloat(self, row, column):
        """Получает число из ячейки таблицы."""

        item = self.tab.tableTargets.item(
            row,
            column,
        )

        if item is None:
            return None

        try:
            return float(
                item.text().replace(",", ".")
            )
        except (TypeError, ValueError):
            return None

    # ==================================================================
    # РАСЧЁТ ФАКТИЧЕСКИХ КООРДИНАТ
    # ==================================================================

    def calculateCoordsTarget(self, rowTarget):
        """
        Вычисляет фактические координаты одной цели
        по таблице инклинометрии.

        Для MD, отсутствующего непосредственно в таблице
        инклинометрии, используется линейная интерполяция.
        """

        md_target = self._getTargetMd(rowTarget)

        if md_target is None:
            return None

        row_after, row_before = (
            self._findInclinometryRows(
                md_target
            )
        )

        if row_after is None:
            self.showWarning(
                "Внимание",
                "MD цели больше, чем максимальный "
                "MD в таблице инклинометрии.",
            )
            return None

        if row_before == row_after:
            return self._getInclinometryCoordinates(
                row_after
            )

        return self._interpolateTargetCoordinates(
            row_before,
            row_after,
            md_target,
        )

    def _getTargetMd(self, row):
        """Получает MD цели из таблицы."""

        item = self.tab.tableTargets.item(
            row,
            self.COL_MD,
        )

        if item is None:
            self.showWarning(
                "Внимание",
                "Введите MD цели в таблице целей.",
            )
            return None

        try:
            return float(
                item.text().replace(",", ".")
            )
        except (TypeError, ValueError):
            return None

    def _findInclinometryRows(self, md_target):
        """
        Находит две соседние точки инклинометрии,
        между которыми находится MD цели.

        Returns:
            row_after, row_before
        """

        table = self.tab.tableInclinometry

        row_after = None
        row_before = None

        for row in range(table.rowCount()):
            md_item = table.item(
                row,
                IncCol["MD"],
            )

            if md_item is None:
                continue

            try:
                md = float(
                    md_item.text().replace(",", ".")
                )
            except (TypeError, ValueError):
                continue

            if md < md_target:
                continue

            if md_target == md:
                row_after = row
                row_before = row
                break

            row_after = row
            row_before = row - 1
            break

        return row_after, row_before

    def _getInclinometryCoordinates(self, row):
        """Получает координаты точки инклинометрии."""

        table = self.tab.tableInclinometry

        north = self._getInclinometryValue(
            table,
            row,
            IncCol["NORTH"],
        )

        east = self._getInclinometryValue(
            table,
            row,
            IncCol["EAST"],
        )

        tvdss = self._getInclinometryValue(
            table,
            row,
            IncCol["TVDSS"],
        )

        if north is None or east is None or tvdss is None:
            return None

        return north, east, tvdss

    @staticmethod
    def _getInclinometryValue(table, row, column):
        """Получает числовое значение из таблицы инклинометрии."""

        item = table.item(row, column)

        if item is None:
            return None

        try:
            return float(
                item.text().replace(",", ".")
            )
        except (TypeError, ValueError):
            return None

    def _interpolateTargetCoordinates(
        self,
        row_before,
        row_after,
        md_target,
    ):
        """
        Линейно интерполирует координаты цели
        между двумя точками инклинометрии.
        """

        table = self.tab.tableInclinometry

        md_before = self._getInclinometryValue(
            table,
            row_before,
            IncCol["MD"],
        )

        north_before = self._getInclinometryValue(
            table,
            row_before,
            IncCol["NORTH"],
        )

        east_before = self._getInclinometryValue(
            table,
            row_before,
            IncCol["EAST"],
        )

        tvdss_before = self._getInclinometryValue(
            table,
            row_before,
            IncCol["TVDSS"],
        )

        md_after = self._getInclinometryValue(
            table,
            row_after,
            IncCol["MD"],
        )

        north_after = self._getInclinometryValue(
            table,
            row_after,
            IncCol["NORTH"],
        )

        east_after = self._getInclinometryValue(
            table,
            row_after,
            IncCol["EAST"],
        )

        tvdss_after = self._getInclinometryValue(
            table,
            row_after,
            IncCol["TVDSS"],
        )

        values = (
            md_before,
            north_before,
            east_before,
            tvdss_before,
            md_after,
            north_after,
            east_after,
            tvdss_after,
        )

        if any(value is None for value in values):
            return None

        if md_after == md_before:
            return None

        k = (
            (md_target - md_before)
            / (md_after - md_before)
        )

        north = (
            north_before
            + k * (north_after - north_before)
        )

        east = (
            east_before
            + k * (east_after - east_before)
        )

        tvdss = (
            tvdss_before
            + k * (tvdss_after - tvdss_before)
        )

        return north, east, tvdss

    # ==================================================================
    # ГОРИЗОНТАЛЬНОЕ ОТКЛОНЕНИЕ
    # ==================================================================

    @staticmethod
    def calculateRfact(
        north_t,
        east_t,
        north_ft,
        east_ft,
    ):
        """
        Рассчитывает горизонтальное отклонение
        проектной цели от фактической точки.
        """

        return sqrt(
            (north_t - north_ft) ** 2
            + (east_t - east_ft) ** 2
        )

    # ==================================================================
    # ДОБАВЛЕНИЕ ФАКТИЧЕСКОЙ ЦЕЛИ В СЛОЙ
    # ==================================================================

    def addActualTargetToLayer(
        self,
        source_row,
        north_f,
        east_f,
        tvdss_f,
    ):
        """
        Добавляет рассчитанную фактическую цель
        в слой welltarget на основе проектной цели.

        Типы:
            0 → 2 — Кровля проект → Кровля факт
            1 → 3 — Подошва проект → Подошва факт
        """

        table = self.tab.tableTargets

        layer_target = (
            self.tab.tabSettingsTargetsMLCBox.currentLayer()
        )

        if not self._validateActualTargetLayer(
            layer_target
        ):
            return False

        target_id = self._getSourceTargetId(
            table,
            source_row,
        )

        if target_id is None:
            return False

        source_target = self._findSourceTarget(
            layer_target,
            target_id,
        )

        if source_target is None:
            self.showWarning(
                "Внимание",
                f"Цель с ID {target_id} не найдена "
                "в слое welltarget.",
            )
            return False

        fact_type = self._getFactTargetType(
            source_target,
            target_id,
        )

        if fact_type is None:
            return False

        actual_target = self._createActualTarget(
            layer_target,
            source_target,
            fact_type,
            north_f,
            east_f,
            tvdss_f,
        )

        if actual_target is None:
            return False

        return self._saveActualTarget(
            layer_target,
            actual_target,
        )

    def _validateActualTargetLayer(self, layer):
        """Проверяет слой welltarget."""

        if layer is None or not layer.isValid():
            self.showWarning(
                "Внимание",
                "Слой целей welltarget не найден.",
            )
            return False

        return True

    def _getSourceTargetId(self, table, row):
        """Получает ID проектной цели из таблицы."""

        id_item = table.item(
            row,
            self.COL_ID,
        )

        if id_item is None or not id_item.text().strip():
            return None

        try:
            return int(id_item.text())
        except (TypeError, ValueError):
            self.showWarning(
                "Внимание",
                "Некорректный ID цели.",
            )
            return None

    def _findSourceTarget(self, layer, target_id):
        """Находит проектную цель по ID."""

        request = QgsFeatureRequest().setFilterExpression(
            f'"id" = {target_id} AND "type" IN (0, 1, 4)'
        )

        return next(
            layer.getFeatures(request),
            None,
        )

    def _getFactTargetType(
        self,
        source_target,
        target_id,
    ):
        """Получает тип фактической цели."""

        source_type = source_target["type"]

        if source_type is None:
            self.showWarning(
                "Внимание",
                f"У цели с ID {target_id} не указан тип.",
            )
            return None

        try:
            source_type = int(source_type)
        except (TypeError, ValueError):
            self.showWarning(
                "Внимание",
                f"Некорректный тип цели с ID {target_id}.",
            )
            return None

        fact_type = self.PROJECT_TO_FACT_TYPE.get(
            source_type
        )

        # Если исходная цель уже фактическая,
        # новую цель не создаём.
        return fact_type

    def _createActualTarget(
        self,
        layer_target,
        source_target,
        fact_type,
        north_f,
        east_f,
        tvdss_f,
    ):
        """
        Создаёт QgsFeature фактической цели.
        """

        actual_target = QgsFeature(
            layer_target.fields()
        )

        # Копируем атрибуты исходной цели,
        # кроме служебных/изменяемых полей.
        for field in layer_target.fields():
            field_name = field.name()

            if field_name in (
                "fid",
                "id",
                "type",
            ):
                continue

            actual_target[field_name] = (
                source_target[field_name]
            )

        actual_target["id"] = (
            self._getNextTargetId(layer_target)
        )

        actual_target["type"] = fact_type

        actual_target["north"] = north_f
        actual_target["east"] = east_f
        actual_target["tvdss"] = tvdss_f

        geometry = self._createTargetGeometry(
            layer_target,
            east_f,
            north_f,
        )

        if geometry is None:
            return None

        actual_target.setGeometry(
            geometry
        )

        return actual_target

    @staticmethod
    def _getNextTargetId(layer):
        """Возвращает следующий ID цели."""

        max_id = 0

        for feature in layer.getFeatures():
            try:
                feature_id = int(
                    feature["id"]
                )
            except (TypeError, ValueError):
                continue

            max_id = max(
                max_id,
                feature_id,
            )

        return max_id + 1

    def _createTargetGeometry(
        self,
        layer_target,
        east_f,
        north_f,
    ):
        """
        Создаёт геометрию фактической цели
        и при необходимости переводит её в CRS слоя.
        """

        point = QgsPointXY(
            east_f,
            north_f,
        )

        crs_calculation = (
            self.crsCurrentTarget
        )

        crs_layer = layer_target.crs()

        if (
            crs_calculation is None
            or not crs_calculation.isValid()
        ):
            self.showWarning(
                "Ошибка",
                "Не определена CRS, в которой "
                "рассчитана фактическая цель.",
            )
            return None

        if (
            crs_layer is None
            or not crs_layer.isValid()
        ):
            self.showWarning(
                "Ошибка",
                "Не определена CRS слоя welltarget.",
            )
            return None

        if crs_calculation != crs_layer:
            try:
                transform = QgsCoordinateTransform(
                    crs_calculation,
                    crs_layer,
                    QgsProject.instance(),
                )

                point = transform.transform(
                    point
                )

            except Exception as error:
                self.showWarning(
                    "Ошибка",
                    "Не удалось преобразовать "
                    f"координаты фактической цели:\n{error}",
                )
                return None

        return QgsGeometry.fromPointXY(
            point
        )

    # ==================================================================
    # СОХРАНЕНИЕ ФАКТИЧЕСКОЙ ЦЕЛИ
    # ==================================================================

    def _saveActualTarget(
        self,
        layer_target,
        actual_target,
    ):
        """
        Добавляет фактическую цель в слой
        и сохраняет изменения.
        """

        layer_target.startEditing()

        success = layer_target.addFeatures(
            [actual_target]
        )

        if not success:
            provider_error = (
                layer_target
                .dataProvider()
                .error()
                .message()
            )

            self._printAddTargetError(
                layer_target,
                actual_target,
                provider_error,
            )

            layer_target.rollBack()

            self.showWarning(
                "Ошибка",
                "Не удалось добавить фактическую "
                "цель в слой welltarget.\n\n"
                f"Ошибка:\n{provider_error}",
            )

            return False

        if not layer_target.commitChanges():
            self.showWarning(
                "Ошибка",
                "Фактическая цель была добавлена, "
                "но не удалось сохранить изменения "
                "в слое welltarget.",
            )
            return False

        layer_target.triggerRepaint()

        return True

    @staticmethod
    def _printAddTargetError(
        layer,
        feature,
        provider_error,
    ):
        """Выводит подробности ошибки добавления цели."""

        print("=" * 40)
        print("ОШИБКА ДОБАВЛЕНИЯ ФАКТИЧЕСКОЙ ЦЕЛИ")
        print("Слой:", layer.name())
        print("ID:", feature["id"])
        print("type:", feature["type"])
        print("north:", feature["north"])
        print("east:", feature["east"])
        print("tvdss:", feature["tvdss"])
        print("Геометрия:", feature.geometry().asWkt())
        print("Ошибка provider:", provider_error)
        print("=" * 40)


    def addEmptyTargetRow(self):
        """Добавляет пустую строку для ручного ввода новой цели."""

        table = self.tab.tableTargets

        row = table.rowCount()
        table.insertRow(row)

        # ID пока пустой.
        # Настоящий ID будет назначен при сохранении цели.
        self._setTableItem(table, row, self.COL_ID, "")
        self._setTableItem(table, row, self.COL_STRATUM, "")
        self._setTableItem(table, row, self.COL_NAME, "")
        self._setTableItem(table, row, self.COL_NORTH, "")
        self._setTableItem(table, row, self.COL_EAST, "")
        self._setTableItem(table, row, self.COL_TVD, "")
        self._setTableItem(table, row, self.COL_TVDSS, "")
        self._setTableItem(table, row, self.COL_MD, "")
        self._setTableItem(table, row, self.COL_NORTH_FACT, "")
        self._setTableItem(table, row, self.COL_EAST_FACT, "")
        self._setTableItem(table, row, self.COL_R_FACT, "")
        self._setTableItem(table, row, self.COL_TVDSS_FACT, "")

        # Делаем строку редактируемой
        for column in range(table.columnCount()):
            item = table.item(row, column)

            if item is None:
                item = QtWidgets.QTableWidgetItem()
                table.setItem(row, column, item)

            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsEditable
            )

        # ID и фактические значения пользователь не редактирует
        for column in (
            self.COL_ID,
            self.COL_NORTH_FACT,
            self.COL_EAST_FACT,
            self.COL_R_FACT,
            self.COL_TVDSS_FACT,
        ):
            item = table.item(row, column)

            if item is not None:
                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEditable
                )

        # Выбираем новую строку
        table.selectRow(row)

        # Сразу ставим курсор в название
        table.setCurrentCell(row, self.COL_NAME)

        item = table.item(row, self.COL_NAME)

        if item is not None:
            table.editItem(item)

    def _getTableText(self, row, column):
        """Возвращает текст из ячейки таблицы."""

        item = self.tab.tableTargets.item(
            row,
            column
        )

        if item is None:
            return ""

        return item.text().strip()


    def _toFloatOrNone(self, value):
        """Преобразует текст в float или возвращает None."""

        if not value:
            return None

        try:
            return float(
                value.replace(",", ".")
            )
        except ValueError:
            return None


    def addTargetsToLayer(self):
        """Добавляет все цели из таблицы как новые объекты welltarget."""

        table = self.tab.tableTargets

        if table.rowCount() == 0:
            QMessageBox.warning(
                self.tab,
                "Добавление целей",
                "В таблице нет целей."
            )
            return

        layer = self.tab.tabSettingsTargetsMLCBox.currentLayer()

        if layer is None:
            QMessageBox.warning(
                self.tab,
                "Добавление целей",
                "Не выбран слой welltarget."
            )
            return

        self.layerTarget = layer

        features = []
        errors = []

        # Первый свободный ID
        next_id = self._getNextTargetId(layer)

        for row in range(table.rowCount()):
            stratum = self._getTableText(row, self.COL_STRATUM)
            name = self._getTableText(row, self.COL_NAME)
            north_text = self._getTableText(row, self.COL_NORTH)
            east_text = self._getTableText(row, self.COL_EAST)
            tvd_text = self._getTableText(row, self.COL_TVD)
            tvdss_text = self._getTableText(row, self.COL_TVDSS)

            if not name:
                errors.append(f"Строка {row + 1}: не указано название")
                continue
            if not north_text or not east_text:
                errors.append(f"Строка {row + 1}: не указаны координаты")
                continue

            try:
                north = float(north_text.replace(",", "."))
                east = float(east_text.replace(",", "."))
            except ValueError:
                errors.append(f"Строка {row + 1}: некорректные координаты")
                continue

            tvd = self._toFloatOrNone(tvd_text)
            tvdss = self._toFloatOrNone(tvdss_text)

            feature = QgsFeature(layer.fields())

            feature["id"] = next_id
            feature["stratum"] = stratum
            feature["name"] = name
            feature["north"] = north
            feature["east"] = east

            if tvd is not None:
                feature["tvd"] = tvd

            if tvdss is not None:
                feature["tvdss"] = tvdss

            # CRS координат таблицы
            if (self.crsCurrentTarget and self.crsCurrentTarget.isValid()):
                feature["crs_text"] = (self.crsCurrentTarget.authid())

            # Тип цели
            feature["type"] = 4

            geometry = self._createTargetGeometry(layer, east, north)

            if geometry.isNull():
                errors.append(f"Строка {row + 1}: не удалось создать геометрию")
                continue

            feature.setGeometry(geometry)
            features.append(feature)
            next_id += 1

        # ---------------------------------
        # Если есть ошибки
        # ---------------------------------

        if errors:
            QMessageBox.warning(
                self.tab,
                "Проверка целей",
                "Исправь следующие строки:\n\n"
                + "\n".join(errors)
            )
            return

        if not features:
            return

        if not layer.isEditable():
            layer.startEditing()

        success = layer.addFeatures(features)
        
        if not success:
            layer.rollBack()
            QMessageBox.critical(self.tab, "Ошибка", "Не удалось добавить цели в слой welltarget.")
            return

        if not layer.commitChanges():
            QMessageBox.critical(
                self.tab,
                "Ошибка",
                "Не удалось сохранить цели."
            )
            return

        layer.triggerRepaint()

        QMessageBox.information(
            self.tab,
            "Цели добавлены",
            f"Добавлено целей: {len(features)}"
        )