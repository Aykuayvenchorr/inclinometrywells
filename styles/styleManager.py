import os


class StyleManager:
    """
    Управляет стилями слоёв плагина.

    Все QML-файлы находятся в папке:
        <plugin>/styles/
    """

    def __init__(self):
        # modules -> inclinometr
        self.plugin_dir = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

        self.styles_dir = os.path.join(
            self.plugin_dir,
            "styles",
        )

    def getStylePath(self, layer_name):
        """
        Возвращает путь к QML-файлу стиля.
        """

        style_path = os.path.join(
            self.styles_dir,
            f"{layer_name}.qml",
        )

        return style_path


    def applyStyle(self, layer, layer_name):
        """
        Применяет QML-стиль к слою.
        """

        if layer is None or not layer.isValid():
            print(
                f"StyleManager: слой '{layer_name}' некорректный."
            )
            return False

        style_path = self.getStylePath(layer_name)

        if not os.path.exists(style_path):
            print(
                f"StyleManager: файл стиля не найден: "
                f"{style_path}"
            )
            return False

        result = layer.loadNamedStyle(style_path)

        if not result:
            print(
                f"StyleManager: ошибка загрузки стиля "
                f"'{style_path}'"
            )
            return False

        layer.triggerRepaint()

        return True

    def applyLayerStyle(self, layer, layer_type):
        """
        Применяет стиль в зависимости от типа слоя.
        """

        styles = {
            "wellhead": "wellhead",
            "welltarget": "welltarget",
            "wellbore": "wellbore",
        }

        style_name = styles.get(layer_type)

        if style_name is None:
            print(
                f"StyleManager: неизвестный тип слоя "
                f"'{layer_type}'."
            )
            return False

        return self.applyStyle(
            layer,
            style_name,
        )