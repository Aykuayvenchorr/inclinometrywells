import json
from pathlib import Path

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsDefaultValue,
    QgsEditorWidgetSetup,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from PyQt5.QtCore import QVariant

from ..styles.styleManager import StyleManager


class TabSettings:
    """Вкладка «Рабочие слои»."""

    DRIVER = "GPKG"
    CRS = "EPSG:4326"
    GPKG_NAME = "InclinometryCalc.gpkg"

    TYPE_FIELDS = (
        ("id", QVariant.Int),
        ("name", QVariant.String),
    )

    WELLHEAD_FIELDS = (
        ("id", QVariant.Int),
        ("type", QVariant.Int),
        ("lic", QVariant.String),
        ("field", QVariant.String),
        ("pad", QVariant.String),
        ("rig", QVariant.String),
        ("name", QVariant.String, 100),
        ("rel", QVariant.Bool),
        ("north", QVariant.Double),
        ("east", QVariant.Double),
        ("alt_ground", QVariant.Double),
        ("alt_rotor", QVariant.Double),
        ("alt", QVariant.Double),
        ("alt_note", QVariant.String),
        ("crs_param", QVariant.String),
        ("crs_text", QVariant.String),
        ("path", QVariant.String),
        ("note", QVariant.String),
    )

    WELLTARGET_FIELDS = (
        ("id", QVariant.Int),
        ("type", QVariant.Int),
        ("lic", QVariant.String),
        ("field", QVariant.String),
        ("stratum", QVariant.String),
        ("pad", QVariant.String),
        ("name", QVariant.String, 100),
        ("num_txt", QVariant.String, 100),
        ("num_int", QVariant.Int),
        ("rel", QVariant.Bool),
        ("north", QVariant.Double),
        ("east", QVariant.Double),
        ("tvd", QVariant.Double),
        ("tvdss", QVariant.Double),
        ("alt_note", QVariant.String),
        ("crs_param", QVariant.String),
        ("crs_text", QVariant.String),
        ("path", QVariant.String),
        ("note", QVariant.String),
    )

    WELLBORE_FIELDS = (
        ("id", QVariant.Int),
        ("type", QVariant.Int),
        ("lic", QVariant.String),
        ("field", QVariant.String),
        ("pad", QVariant.String),
        ("name", QVariant.String, 100),
        ("wellhead_id", QVariant.Int),
        ("welltarget", QVariant.String, 100),
        ("rel", QVariant.Bool),
        ("note", QVariant.String),
    )

    WELLHEAD_TYPES = {
        0: "Позиция",
        1: "Устье",
    }

    WELLTARGET_TYPES = {
        0: "Кровля проект",
        1: "Подошва проект",
        2: "Кровля факт",
        3: "Подошва факт",
    }

    WELLBORE_TYPES = {
        0: "Основной проектный",
        1: "Основной фактический",
        2: "Вероятный верх",
        3: "Вероятный запад",
        4: "Вероятный низ",
        5: "Вероятный восток",
    }

    def __init__(self, dialog):
        self.tab = dialog
        self.gpkg_path = ""
        self.wellhead_name = ""
        self.welltarget_name = ""
        self.wellbore_name = ""
        self._wellhead_signals_connected = False

        self.read_settings()
        self.styleManager = StyleManager()

    # ------------------------------------------------------------------
    # Settings / paths
    # ------------------------------------------------------------------

    def read_settings(self):
        """Читает названия рабочих слоёв из settings/config.json."""
        base_dir = Path(__file__).resolve().parent.parent
        config_path = base_dir / "settings" / "config.json"

        with config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)

        self.wellhead_name = config["wellhead"]
        self.welltarget_name = config["welltarget"]
        self.wellbore_name = config["wellbore"]

    def pathTodDB(self, workdir):
        """Формирует путь к GeoPackage."""
        self.gpkg_path = str(Path(workdir) / self.GPKG_NAME)

        # if Path(self.gpkg_path).is_file():
        #     print("База существует:", self.gpkg_path)
        # else:
        #     print("База будет создана:", self.gpkg_path)

        return self.gpkg_path

    def _get_workdir(self):
        """Возвращает рабочую директорию или показывает ошибку."""
        workdir = self.tab.tabSettingsWorkdir.filePath()

        if not workdir or not Path(workdir).is_dir():
            QMessageBox.critical(
                self.tab,
                "Рабочая папка",
                "Не указана рабочая папка!",
            )
            return None

        return workdir

    # ------------------------------------------------------------------
    # Layer lookup / loading
    # ------------------------------------------------------------------

    def getLayer(self, layer_name):
        """Возвращает загруженный из текущего GPKG слой."""
        if not self.gpkg_path:
            return None

        for layer in QgsProject.instance().mapLayers().values():
            if (
                layer.name() == layer_name
                and layer.source().startswith(self.gpkg_path)
            ):
                return layer

        return None

    def getWellheadLayer(self):
        return self.getLayer(self.wellhead_name)

    def getWelltargetLayer(self):
        return self.getLayer(self.welltarget_name)

    def getWellboreLayer(self):
        return self.getLayer(self.wellbore_name)

    def _load_gpkg_layer(self, layer_name):
        """Открывает слой из текущего GeoPackage."""
        if not Path(self.gpkg_path).is_file():
            return None

        uri = f"{self.gpkg_path}|layername={layer_name}"
        layer = QgsVectorLayer(uri, layer_name, "ogr")

        return layer if layer.isValid() else None

    def loadTypeLayer(self, layer_name):
        """
        Загружает справочник типов из текущего GeoPackage в проект QGIS.
        Если слой уже загружен — повторно не добавляет.
        """
        if not Path(self.gpkg_path).is_file():
            return None

        loaded_layer = self.getLayer(layer_name)
        if loaded_layer is not None:
            return loaded_layer

        layer = self._load_gpkg_layer(layer_name)
        if layer is None:
            return None

        QgsProject.instance().addMapLayer(layer)
        return layer

    # ------------------------------------------------------------------
    # GPKG creation
    # ------------------------------------------------------------------

    def _create_fields(self, field_definitions):
        """Создаёт QgsFields из описания полей."""
        fields = QgsFields()

        for field_definition in field_definitions:
            name, field_type, *length = field_definition

            if length:
                fields.append(QgsField(name, field_type, len=length[0]))
            else:
                fields.append(QgsField(name, field_type))

        return fields

    def _create_gpkg_layer(self, layer_name, fields, geometry_type, crs=None):
        """
        Создаёт слой в GeoPackage и возвращает True/False.
        """
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = self.DRIVER
        options.layerName = layer_name

        if Path(self.gpkg_path).is_file():
            options.actionOnExistingFile = (
                QgsVectorFileWriter.CreateOrOverwriteLayer
            )

        crs = crs or QgsCoordinateReferenceSystem()
        transform_context = QgsProject.instance().transformContext()

        writer = QgsVectorFileWriter.create(
            self.gpkg_path,
            fields,
            geometry_type,
            crs,
            transform_context,
            options,
        )

        if writer.hasError() != QgsVectorFileWriter.NoError:
            QMessageBox.critical(
                self.tab,
                "Ошибка создания слоя",
                f"Не удалось создать слой {layer_name}:\n"
                f"{writer.errorMessage()}",
            )
            del writer
            return False

        del writer
        return True

    def _create_type_layer(self, layer_name, values):
        """Создаёт справочник типов и заполняет его."""
        existing_layer = self._load_gpkg_layer(layer_name)

        if existing_layer is not None:
            # print(f"{layer_name} уже существует в БД.")
            return existing_layer

        fields = self._create_fields(self.TYPE_FIELDS)

        if not self._create_gpkg_layer(
            layer_name,
            fields,
            QgsWkbTypes.NoGeometry,
        ):
            return None

        layer = self._load_gpkg_layer(layer_name)

        if layer is None:
            QMessageBox.critical(
                self.tab,
                "Ошибка",
                f"Слой {layer_name} создан, "
                "но не удалось его загрузить.",
            )
            return None

        layer.startEditing()

        for type_id, type_name in values.items():
            feature = QgsFeature(layer.fields())
            feature["id"] = type_id
            feature["name"] = type_name
            layer.addFeature(feature)

        if not layer.commitChanges():
            QMessageBox.warning(
                self.tab,
                "Предупреждение",
                f"Не удалось сохранить справочник {layer_name}.",
            )

        # print(f"{layer_name} создан и заполнен.")
        return layer

    # ------------------------------------------------------------------
    # Type fields
    # ------------------------------------------------------------------

    def setupTypeField(self, layer, type_layer_name, default_value="0"):
        """Настраивает поле type через ValueMap."""
        field_index = layer.fields().indexOf("type")

        if field_index == -1:
            # print(f"Поле type отсутствует в слое {layer.name()}.")
            return

        type_layer = self.loadTypeLayer(type_layer_name)

        if type_layer is None:
            # print(
            #     f"{type_layer_name} отсутствует "
            #     "или не удалось его открыть."
            # )
            return

        value_map = []

        for feature in type_layer.getFeatures():
            type_id = feature["id"]
            type_name = feature["name"]

            if type_id is None or type_name is None:
                continue

            value_map.append({str(type_name): type_id})

        if not value_map:
            # print(f"В {type_layer_name} нет записей.")
            return

        layer.setEditorWidgetSetup(
            field_index,
            QgsEditorWidgetSetup("ValueMap", {"map": value_map}),
        )
        layer.setDefaultValueDefinition(
            field_index,
            QgsDefaultValue(str(default_value)),
        )

    def setupWellheadTypeField(self, layer):
        self.setupTypeField(layer, "wellhead_type")

    def setupWelltargetTypeField(self, layer):
        self.setupTypeField(layer, "welltarget_type")

    def setupWellboreTypeField(self, layer):
        self.setupTypeField(layer, "wellbore_type")

    def _set_rel_default(self, layer):
        """Устанавливает rel=True по умолчанию."""
        field_index = layer.fields().indexOf("rel")

        if field_index != -1:
            layer.setDefaultValueDefinition(
                field_index,
                QgsDefaultValue("true"),
            )

    # ------------------------------------------------------------------
    # Wellhead relation
    # ------------------------------------------------------------------

    def setupWellboreWellheadField(self, layer):
        """Настраивает wellhead_id как ValueMap из слоя wellhead."""
        field_index = layer.fields().indexOf("wellhead_id")

        if field_index == -1:
            # print("Поле wellhead_id отсутствует.")
            return

        value_map = []
        wellhead_layer = self.getWellheadLayer()

        if wellhead_layer is not None and wellhead_layer.isValid():
            has_id = wellhead_layer.fields().indexOf("id") != -1
            has_name = wellhead_layer.fields().indexOf("name") != -1

            if has_id and has_name:
                for feature in wellhead_layer.getFeatures():
                    wellhead_id = feature["id"]
                    wellhead_name = feature["name"]

                    if wellhead_id is None:
                        continue

                    wellhead_name = (
                        "" if wellhead_name is None else str(wellhead_name)
                    )
                    display_name = f"{wellhead_name} ({wellhead_id})"

                    value_map.append({display_name: wellhead_id})

        layer.setEditorWidgetSetup(
            field_index,
            QgsEditorWidgetSetup("ValueMap", {"map": value_map}),
        )
        layer.updateFields()

    def updateWellboreWellheadField(self):
        """Обновляет список значений wellhead_id."""
        wellbore_layer = self.getWellboreLayer()

        if wellbore_layer is not None:
            self.setupWellboreWellheadField(wellbore_layer)

    # ------------------------------------------------------------------
    # Common layer creation / setup
    # ------------------------------------------------------------------

    def _prepare_layer(self, layer, layer_kind):
        """Добавляет слой в проект и выполняет общую настройку."""
        QgsProject.instance().addMapLayer(layer)
        self.styleManager.applyLayerStyle(layer, layer_kind)
        self._set_rel_default(layer)

    def _load_or_create_layer(
        self,
        layer_name,
        fields,
        geometry_type,
        layer_kind,
    ):
        """
        Загружает существующий слой из GPKG или создаёт новый.
        Возвращает слой либо None.
        """
        loaded_layer = self.getLayer(layer_name)

        if loaded_layer is not None:
            return loaded_layer

        existing_layer = self._load_gpkg_layer(layer_name)

        if existing_layer is not None:
            self._prepare_layer(existing_layer, layer_kind)
            return existing_layer

        crs = QgsCoordinateReferenceSystem(self.CRS)

        if not self._create_gpkg_layer(
            layer_name,
            fields,
            geometry_type,
            crs,
        ):
            return None

        layer = self._load_gpkg_layer(layer_name)

        if layer is None:
            QMessageBox.critical(
                self.tab,
                "Ошибка",
                f"Слой {layer_name} создан, "
                "но не удалось его загрузить.\n\n"
                f"Ошибка: {layer.error().message()}",
            )
            return None

        self._prepare_layer(layer, layer_kind)
        return layer

    # ------------------------------------------------------------------
    # Wellhead
    # ------------------------------------------------------------------

    def wellheadLayerAdd(self):
        """Создаёт или загружает слой wellhead."""
        workdir = self._get_workdir()

        if workdir is None:
            return

        self.pathTodDB(workdir)

        self._create_type_layer(
            "wellhead_type",
            self.WELLHEAD_TYPES,
        )
        self.loadTypeLayer("wellhead_type")

        layer = self._load_or_create_layer(
            self.wellhead_name,
            self._create_fields(self.WELLHEAD_FIELDS),
            QgsWkbTypes.Point,
            "wellhead",
        )

        if layer is None:
            return

        self.setupWellheadTypeField(layer)
        self.tab.tabSettingsWellheadMLCBox.setLayer(layer)

        if self.getWellheadLayer() is layer:
            self.connectWellheadSignals()
            self.updateWellboreWellheadField()

        if layer.id() not in QgsProject.instance().mapLayers():
            return

        # if layer.id() in QgsProject.instance().mapLayers():
        #     # Если слой был загружен через _load_or_create_layer,
        #     # сообщение зависит от того, существовал ли он раньше.
        #     QMessageBox.information(
        #         self.tab,
        #         "Слой wellhead",
        #         f"Слой {self.wellhead_name} готов к работе.",
        #     )

    # ------------------------------------------------------------------
    # Welltarget
    # ------------------------------------------------------------------

    def welltargetLayerAdd(self):
        """Создаёт или загружает слой welltarget."""
        workdir = self._get_workdir()

        if workdir is None:
            return

        self.pathTodDB(workdir)

        self._create_type_layer(
            "welltarget_type",
            self.WELLTARGET_TYPES,
        )
        self.loadTypeLayer("welltarget_type")

        layer = self._load_or_create_layer(
            self.welltarget_name,
            self._create_fields(self.WELLTARGET_FIELDS),
            QgsWkbTypes.Point,
            "welltarget",
        )

        if layer is None:
            return

        self.setupWelltargetTypeField(layer)
        self.tab.tabSettingsTargetsMLCBox.setLayer(layer)

        # QMessageBox.information(
        #     self.tab,
        #     "Слой welltarget",
        #     f"Слой {self.welltarget_name} готов к работе.",
        # )

    # ------------------------------------------------------------------
    # Wellbore
    # ------------------------------------------------------------------

    def wellboreLayerAdd(self):
        """Создаёт или загружает слой wellbore."""
        workdir = self._get_workdir()

        if workdir is None:
            return

        self.pathTodDB(workdir)

        self._create_type_layer(
            "wellbore_type",
            self.WELLBORE_TYPES,
        )
        self.loadTypeLayer("wellbore_type")

        layer = self._load_or_create_layer(
            self.wellbore_name,
            self._create_fields(self.WELLBORE_FIELDS),
            QgsWkbTypes.LineStringZ,
            "wellbore",
        )

        if layer is None:
            return

        self.setupWellboreTypeField(layer)
        self.setupWellboreWellheadField(layer)
        self.tab.tabSettingsBoresMLCBox.setLayer(layer)

        self.connectWellheadSignals()

        # QMessageBox.information(
        #     self.tab,
        #     "Слой wellbore",
        #     f"Слой {self.wellbore_name} готов к работе.",
        # )

    # ------------------------------------------------------------------
    # ComboBox helpers
    # ------------------------------------------------------------------

    def selectWellheadInComboBox(self):
        layer = self.getWellheadLayer()

        if layer is not None:
            self.tab.tabSettingsWellheadMLCBox.setLayer(layer)

    def selectWelltargetInComboBox(self):
        layer = self.getWelltargetLayer()

        if layer is not None:
            self.tab.tabSettingsTargetsMLCBox.setLayer(layer)

    def selectWellboreInComboBox(self):
        layer = self.getWellboreLayer()

        if layer is not None:
            self.tab.tabSettingsBoresMLCBox.setLayer(layer)

    def _filter_combo(self, combo, required_fields, geometry_type):
        """Исключает из ComboBox слои неподходящего типа/структуры."""
        excepted_layers = []

        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                excepted_layers.append(layer)
                continue

            if layer.geometryType() != geometry_type:
                excepted_layers.append(layer)
                continue

            layer_fields = {field.name() for field in layer.fields()}

            if not required_fields.issubset(layer_fields):
                excepted_layers.append(layer)

        combo.setExceptedLayerList(excepted_layers)

    def filterWellheadLayers(self):
        required_fields = {
            "id", "type", "lic", "field", "pad", "rig", "name",
            "rel", "north", "east", "alt_ground", "alt_rotor", "alt",
            "alt_note", "crs_param", "crs_text", "path", "note",
        }

        self._filter_combo(
            self.tab.tabSettingsWellheadMLCBox,
            required_fields,
            QgsWkbTypes.PointGeometry,
        )

    def filterWelltargetLayers(self):
        required_fields = {
            "id", "type", "lic", "field", "stratum", "pad", "name",
            "num_txt", "num_int", "rel", "north", "east", "tvd",
            "tvdss", "alt_note", "crs_param", "crs_text", "path", "note",
        }

        self._filter_combo(
            self.tab.tabSettingsTargetsMLCBox,
            required_fields,
            QgsWkbTypes.PointGeometry,
        )

    def filterWellboreLayers(self):
        required_fields = {
            "id", "type", "lic", "field", "pad", "name",
            "wellhead_id", "welltarget", "rel", "note",
        }

        self._filter_combo(
            self.tab.tabSettingsBoresMLCBox,
            required_fields,
            QgsWkbTypes.LineGeometry,
        )

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def connectWellheadSignals(self):
        """Подключает сигналы wellhead только один раз."""
        wellhead_layer = self.getWellheadLayer()

        if wellhead_layer is None:
            # print("wellhead не найден.")
            return

        if self._wellhead_signals_connected:
            return

        wellhead_layer.featureAdded.connect(self._onWellheadChanged)
        wellhead_layer.featureDeleted.connect(self._onWellheadChanged)
        wellhead_layer.attributeValueChanged.connect(
            self._onWellheadAttributeChanged
        )

        self._wellhead_signals_connected = True
        # print("Сигналы wellhead подключены.")

    def _onWellheadChanged(self, fid):
        self.updateWellboreWellheadField()

    def _onWellheadAttributeChanged(self, fid, field, value):
        self.updateWellboreWellheadField()

    def _onLayersChanged(self, *args):
        """Обновляет фильтрацию ComboBox после изменения проекта."""
        self.filterWellheadLayers()
        self.filterWelltargetLayers()
        self.filterWellboreLayers()

    # ------------------------------------------------------------------
    # Validation / tabs
    # ------------------------------------------------------------------

    def wellheadTabActivate(self):
        """Активирует вкладку позиций/устьев."""
        if self.checkSelectedLayers():
            index = self.tab.tabWidget.indexOf(self.tab.tabWellheads)
            self.tab.tabWidget.setTabEnabled(index, True)
            self.tab.tabWidget.setCurrentWidget(self.tab.tabWellheads)

    def checkSelectedLayers(self) -> bool:
        """Проверяет выбор слоёв wellhead, welltarget и wellbore."""
        layer_checks = (
            (
                self.tab.tabSettingsWellheadMLCBox.currentLayer(),
                "Сначала выберите слой позиций/устьев.",
            ),
            (
                self.tab.tabSettingsTargetsMLCBox.currentLayer(),
                "Сначала выберите слой целей.",
            ),
            (
                self.tab.tabSettingsBoresMLCBox.currentLayer(),
                "Сначала выберите слой стволов.",
            ),
        )

        for layer, message in layer_checks:
            if layer is None:
                QMessageBox.warning(
                    self.tab,
                    "Внимание",
                    message,
                )
                return False

        return True
