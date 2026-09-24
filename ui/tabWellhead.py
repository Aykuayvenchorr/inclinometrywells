from qgis.PyQt.QtWidgets import QMessageBox

from qgis.core import (
    QgsProject,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsCoordinateReferenceSystem,
)

from qgis.gui import QgsMapToolIdentifyFeature
from qgis.utils import iface
from ..modules.geodezy import Geodezy


class TabWellhead:
    """Вкладка Позиции/Устье."""

    # Поля, необходимые для работы с wellhead.
    REQUIRED_FIELDS = {
        "name",
        "alt_ground",
        "alt_rotor",
        "lic",
        "east",
        "north",
        "crs_text",
    }

    # Форматы отображения координат.
    GEOGRAPHIC_DECIMALS = 10
    PROJECTED_DECIMALS = 3

    def __init__(self, dialog):
        self.tab = dialog

        self.crsLayerWellHead = None
        self.crsOutputWellHead = None
        self.layerWellHead = None

        self.wellHeadIdentifyTool = None

        # Выбранное устье хранится в основном диалоге.
        self.tab.selectedWellHead = None

    # ==================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ==================================================================

    def showWarning(self, title, message):
        """Показывает предупреждение пользователю."""
        QMessageBox.warning(
            self.tab,
            title,
            message,
        )

    def getCoordinateSource(self):
        """
        Возвращает источник координат.

        Returns:
            "map"   — координаты из геометрии;
            "value" — координаты из атрибутов;
            None    — источник не выбран.
        """

        if self.tab.tabWellheadsCRSMapBtn.isChecked():
            return "map"

        if self.tab.tabWellheadsCRSValueBtn.isChecked():
            return "value"

        self.showWarning(
            "Внимание",
            "Выберите способ получения координат.",
        )

        return None

    def getCoordinatesSource(self):
        """
        Совместимость со старым кодом.

        Старое имя метода оставлено, чтобы не сломать
        существующие подключения.
        """
        return self.getCoordinateSource()

    def checkCoordinateMethod(self):
        """
        Совместимость со старым кодом.

        Возвращает выбранный источник координат.
        """
        return self.getCoordinateSource()

    def validateLayer(self, layer):
        """
        Проверяет наличие и корректность слоя.
        """

        if layer is None:
            self.showWarning(
                "Внимание",
                "Сначала выберите слой wellhead в настройках.",
            )
            return False

        if not layer.isValid():
            self.showWarning(
                "Внимание",
                "Выбранный слой недействителен.",
            )
            return False

        return True

    def validateRequiredFields(self, layer):
        """
        Проверяет наличие необходимых полей в слое.
        """

        layer_fields = {
            field.name()
            for field in layer.fields()
        }

        missing_fields = self.REQUIRED_FIELDS - layer_fields

        if missing_fields:
            self.showWarning(
                "Ошибка",
                "В слое wellhead отсутствуют поля:\n"
                + "\n".join(sorted(missing_fields)),
            )
            return False

        return True

    def validateGeometry(self, feature):
        """
        Проверяет наличие непустой геометрии.
        """

        geometry = feature.geometry()

        if geometry is None or geometry.isNull() or geometry.isEmpty():
            self.showWarning(
                "Ошибка",
                "У выбранного объекта отсутствует геометрия.",
            )
            return False

        return True

    def setProjectionWidgetCrs(self, crs):
        """Устанавливает CRS в виджет выбора системы координат."""

        self.tab.mQgsProjectionSelectionWidgetWellHead.setCrs(crs)

    # ==================================================================
    # ВЫБОР WELLHEAD
    # ==================================================================

    def selectWellHead(self):
        """
        Запускает выбор объекта wellhead на карте.

        Слой берётся из:
            tabSettingsWellheadMLCBox
        """

        coordinate_source = self.getCoordinateSource()

        if coordinate_source is None:
            return

        layer = self.tab.tabSettingsWellheadMLCBox.currentLayer()

        if not self.validateLayer(layer):
            return

        self.layerWellHead = layer

        # Исходная CRS слоя.
        self.crsLayerWellHead = layer.crs()

        # Изначально расчёт выполняется в CRS слоя.
        self.crsOutputWellHead = layer.crs()

        # Показываем CRS слоя.
        self.setProjectionWidgetCrs(
            self.crsOutputWellHead
        )

        # Создаём инструмент идентификации.
        self.wellHeadIdentifyTool = QgsMapToolIdentifyFeature(
            iface.mapCanvas()
        )

        self.wellHeadIdentifyTool.setLayer(layer)

        self.wellHeadIdentifyTool.featureIdentified.connect(
            self.wellHeadSelected
        )

        # Активируем инструмент на карте.
        iface.mapCanvas().setMapTool(
            self.wellHeadIdentifyTool
        )

    # ==================================================================
    # ОБРАБОТКА ВЫБРАННОГО WELLHEAD
    # ==================================================================

    def wellHeadSelected(self, feature):
        """
        Обрабатывает выбранный объект wellhead.
        """

        self.tab.selectedWellHead = feature

        if self.layerWellHead is None:
            self.showWarning(
                "Внимание",
                "Слой wellhead не определён.",
            )
            return

        if not self.validateRequiredFields(
            self.layerWellHead
        ):
            return

        self.fillWellHeadInfo(feature)

        # Проверяем альтитуды.
        # Существующая логика сохраняется:
        # если значение отсутствует, пользователю показывается
        # предупреждение и записывается 0.0.
        self.checkWellHeadAltitudes()

        if not self.validateGeometry(feature):
            return

        coordinate_source = self.getCoordinateSource()

        if coordinate_source is None:
            return

        if coordinate_source == "map":
            coordinates = self.getCoordinatesFromGeometry(
                feature
            )
        else:
            coordinates = self.getCoordinatesFromAttributes(
                feature
            )

        if coordinates is None:
            return

        east, north, source_crs = coordinates

        # Обновляем CRS источника координат.
        self.crsLayerWellHead = source_crs

        self.setProjectionWidgetCrs(source_crs)

        # Преобразуем координаты в текущую CRS расчёта.
        target_point = self.transformCoordinates(
            east,
            north,
            source_crs,
            self.crsOutputWellHead,
        )

        if target_point is None:
            return

        # Показываем координаты.
        self.setCoordinateValues(target_point)

        # Завершаем выбор объекта.
        self.disableIdentifyTool()

        # Разрешаем изменение CRS.
        self.tab.mQgsProjectionSelectionWidgetWellHead.setEnabled(
            True
        )

    # ==================================================================
    # ЗАПОЛНЕНИЕ ИНФОРМАЦИИ О WELLHEAD
    # ==================================================================

    def fillWellHeadInfo(self, feature):
        """
        Заполняет поля информации об устье.
        """

        self.tab.txtWellHeadName.setText(
            self.fieldToString(
                feature["name"]
            )
        )

        self.tab.txtWellHeadGround.setText(
            self.fieldToString(
                feature["alt_ground"]
            )
        )

        self.tab.txtWellHeadRotor.setText(
            self.fieldToString(
                feature["alt_rotor"]
            )
        )

        self.tab.txtWellHeadLicense.setText(
            self.fieldToString(
                feature["lic"]
            )
        )

    @staticmethod
    def fieldToString(value):
        """
        Преобразует значение атрибута в строку.

        None и пустые значения превращаются в "".
        """
        return str(value or "")

    # ==================================================================
    # ПОЛУЧЕНИЕ КООРДИНАТ
    # ==================================================================

    def getCoordinatesFromGeometry(self, feature):
        """
        Получает координаты из геометрии объекта.

        Returns:
            (east, north, crs)
            или None при ошибке.
        """

        geometry = feature.geometry()

        if geometry is None or geometry.isNull() or geometry.isEmpty():
            self.showWarning(
                "Ошибка",
                "У выбранного объекта отсутствует геометрия.",
            )
            return None

        if not geometry.isMultipart():
            point = geometry.asPoint()
        else:
            points = geometry.asMultiPoint()

            if not points:
                self.showWarning(
                    "Ошибка",
                    "Не удалось получить точку из геометрии.",
                )
                return None

            point = points[0]

        east = point.x()
        north = point.y()

        return (
            east,
            north,
            self.crsLayerWellHead,
        )

    def getCoordinatesFromAttributes(self, feature):
        """
        Получает координаты east/north из атрибутов
        и CRS из поля crs_text.

        Returns:
            (east, north, crs)
            или None при ошибке.
        """

        east = feature["east"]
        north = feature["north"]

        if east is None or north is None:
            self.showWarning(
                "Ошибка",
                "В атрибутах выбранного объекта отсутствуют "
                "координаты east/north.",
            )
            return None

        try:
            east = float(east)
            north = float(north)

        except (TypeError, ValueError):
            self.showWarning(
                "Ошибка",
                "Значения полей east и north должны быть "
                "числовыми.",
            )
            return None

        crs = self.getFeatureCrs(feature)

        if crs is None:
            return None

        return east, north, crs

    def getFeatureCrs(self, feature):
        """
        Получает CRS из поля crs_text.
        """

        crs_value = feature["crs_text"]

        if crs_value is None:
            self.showWarning(
                "Ошибка",
                "В атрибутах выбранного объекта не указана "
                "система координат в поле crs_text.",
            )
            return None

        crs_text = str(crs_value).strip()

        if not crs_text:
            self.showWarning(
                "Ошибка",
                "В атрибутах выбранного объекта не указана "
                "система координат в поле crs_text.",
            )
            return None

        crs = QgsCoordinateReferenceSystem(
            crs_text
        )

        if not crs.isValid():
            self.showWarning(
                "Ошибка",
                f"Не удалось определить систему координат:\n"
                f"{crs_text}",
            )
            return None

        return crs

    # ==================================================================
    # ПРЕОБРАЗОВАНИЕ КООРДИНАТ
    # ==================================================================

    def transformCoordinates(
        self,
        east,
        north,
        source_crs,
        target_crs,
    ):
        """
        Преобразует координаты из source_crs в target_crs.
        """

        if source_crs is None or not source_crs.isValid():
            self.showWarning(
                "Ошибка",
                "Исходная система координат недействительна.",
            )
            return None

        if target_crs is None or not target_crs.isValid():
            self.showWarning(
                "Ошибка",
                "Целевая система координат недействительна.",
            )
            return None

        try:
            transform = QgsCoordinateTransform(
                source_crs,
                target_crs,
                QgsProject.instance(),
            )

            source_point = QgsPointXY(
                east,
                north,
            )

            return transform.transform(
                source_point
            )

        except Exception as error:
            self.showWarning(
                "Ошибка",
                "Не удалось преобразовать координаты:\n"
                f"{error}",
            )
            return None

    def setCoordinateValues(self, point):
        """
        Записывает преобразованные координаты
        в поля интерфейса.
        """

        if self.crsOutputWellHead is None:
            return

        if self.crsOutputWellHead.isGeographic():
            decimals = self.GEOGRAPHIC_DECIMALS
        else:
            decimals = self.PROJECTED_DECIMALS

        self.tab.txtWellHeadNorth.setText(
            f"{point.y():.{decimals}f}"
        )

        self.tab.txtWellHeadEast.setText(
            f"{point.x():.{decimals}f}"
        )

    # ==================================================================
    # АЛЬТИТУДЫ
    # ==================================================================

    def checkWellHeadAltitudes(self):
        """
        Проверяет наличие альтитуд земли и ротора.

        Если значение отсутствует, устанавливает 0.0.
        """

        valid = True

        if self.tab.txtWellHeadGround.text() == "":
            self.showWarning(
                "Внимание",
                "В данных позиции / устья "
                "отсутствует альтитуда земли.",
            )

            self.tab.txtWellHeadGround.setText(
                "0.0"
            )

            valid = False

        if self.tab.txtWellHeadRotor.text() == "":
            self.showWarning(
                "Внимание",
                "В данных позиции / устья "
                "отсутствует альтитуда ротора.",
            )

            self.tab.txtWellHeadRotor.setText(
                "0.0"
            )

            valid = False

        return valid

    # ==================================================================
    # ИЗМЕНЕНИЕ CRS
    # ==================================================================

    def wellHeadCrsChanged(self, crs):
        """
        Обрабатывает изменение системы координат расчёта.
        """

        # Предыдущая CRS становится исходной,
        # новая CRS становится целевой.
        previous_crs = self.crsOutputWellHead

        self.crsLayerWellHead = previous_crs
        self.crsOutputWellHead = crs

        # Обновляем доступность инклинометрии.
        self.updateInclState()

        # Если координаты ещё не выбраны,
        # преобразовывать нечего.
        if not self.hasCoordinateValues():
            return

        try:
            north = float(
                self.tab.txtWellHeadNorth.text()
            )

            east = float(
                self.tab.txtWellHeadEast.text()
            )

        except (TypeError, ValueError):
            self.showWarning(
                "Ошибка",
                "Текущие координаты имеют некорректный "
                "числовой формат.",
            )
            return

        target_point = self.transformCoordinates(
            east,
            north,
            self.crsLayerWellHead,
            self.crsOutputWellHead,
        )

        if target_point is None:
            return

        self.setCoordinateValues(
            target_point
        )

    def hasCoordinateValues(self):
        """
        Проверяет, заполнены ли координаты в интерфейсе.
        """

        north = self.tab.txtWellHeadNorth.text().strip()
        east = self.tab.txtWellHeadEast.text().strip()

        return bool(north and east)

    # ==================================================================
    # ИНСТРУМЕНТ ВЫБОРА НА КАРТЕ
    # ==================================================================

    def disableIdentifyTool(self):
        """
        Отключает инструмент выбора wellhead.
        """

        if self.wellHeadIdentifyTool is None:
            return

        iface.mapCanvas().unsetMapTool(
            self.wellHeadIdentifyTool
        )

    # ==================================================================
    # ТЕКУЩАЯ CRS
    # ==================================================================

    def getCurrentCrs(self):
        """
        Возвращает текущую систему координат
        для расчёта.
        """

        return self.crsOutputWellHead

    # ==================================================================
    # ВКЛАДКА ИНКЛИНОМЕТРИИ
    # ==================================================================

    def inclTabActivate(self):
        """
        Переходит на вкладку инклинометрии.

        Вкладка должна быть предварительно разрешена
        методом updateInclState().
        """

        if not self.tab.selectedWellHead:
            self.showWarning(
                "Внимание",
                "Выберите позицию",
            )
            return

        self.tab.tabWidget.setCurrentWidget(
            self.tab.tabIncls
        )


    # ==================================================================
    # СОСТОЯНИЕ ВКЛАДКИ ИНКЛИНОМЕТРИИ
    # ==================================================================

    def updateInclState(self):
        """
        Включает/выключает возможность перехода
        к расчёту инклинометрии в зависимости от CRS.
        """

        projection_type = Geodezy.getProjectionType(self.crsOutputWellHead)

        enabled = projection_type is not None

        if not enabled:
            self.showWarning(
                "Внимание",
                "Для расчёта инклинометрии необходимо "
                "выбрать систему координат UTM "
                "или Гаусса-Крюгера.",
            )

        incls_index = self.tab.tabWidget.indexOf(
            self.tab.tabIncls
        )

        self.tab.tabWidget.setTabEnabled(
            incls_index,
            enabled,
        )

        self.tab.tabWellheadInclGoBtn.setEnabled(
            enabled
        )