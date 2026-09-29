from math import (
    acos,
    cos,
    degrees,
    isclose,
    radians,
    sin,
    sqrt,
    tan,
)


class Inclinometry:
    """
    Расчёты траектории скважины по данным инклинометрии.
    """

    # ==================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ==================================================================

    @staticmethod
    def cross360(
        azimuth_grid_start: float,
        azimuth_grid_end: float,
    ) -> float:
        """
        Рассчитывает средний дирекционный угол с учётом
        перехода через 0°/360°.

        Углы на входе и выходе — в радианах.
        """

        start_deg = degrees(azimuth_grid_start) % 360.0
        end_deg = degrees(azimuth_grid_end) % 360.0

        delta_deg = end_deg - start_deg

        if delta_deg > 180.0:
            delta_deg -= 360.0

        elif delta_deg < -180.0:
            delta_deg += 360.0

        mean_deg = (
            start_deg
            + delta_deg / 2.0
        ) % 360.0

        return radians(mean_deg)

    @staticmethod
    def _calculate_beta(
        azimuth_grid_start: float,
        azimuth_grid_end: float,
        zenith_start: float,
        zenith_end: float,
    ) -> float:
        """
        Рассчитывает угол между направлениями ствола β.
        """

        cos_beta = (
            cos(zenith_end - zenith_start)
            - sin(zenith_start)
            * sin(zenith_end)
            * (
                1.0
                - cos(
                    azimuth_grid_end
                    - azimuth_grid_start
                )
            )
        )

        # Защита от ошибок вычислений:
        # acos() принимает только [-1, 1].
        cos_beta = max(
            -1.0,
            min(1.0, cos_beta),
        )

        return acos(cos_beta)

    # ==================================================================
    # МЕТОД СРЕДНИХ УГЛОВ
    # ==================================================================

    def method_mean_angle(
        self,
        dl: float,
        azimuth_grid_start: float,
        azimuth_grid_end: float,
        zenith_start: float,
        zenith_end: float,
    ) -> tuple[float, float, float]:
        """
        Рассчитывает приращения методом средних углов.

        Параметры
        ----------
        dl : float
            Приращение длины, м.

        azimuth_grid_start : float
            Дирекционный угол начала интервала, радианы.

        azimuth_grid_end : float
            Дирекционный угол конца интервала, радианы.

        zenith_start : float
            Зенитный угол начала интервала, радианы.

        zenith_end : float
            Зенитный угол конца интервала, радианы.

        Returns
        -------
        tuple[float, float, float]
            dNorth, dEast, dZ.
        """

        azimuth_mean = self.cross360(
            azimuth_grid_start,
            azimuth_grid_end,
        )

        zenith_mean = (
            zenith_start
            + zenith_end
        ) / 2.0

        dNorth = (
            dl
            * sin(zenith_mean)
            * cos(azimuth_mean)
        )

        dEast = (
            dl
            * sin(zenith_mean)
            * sin(azimuth_mean)
        )

        dZ = (
            dl
            * cos(zenith_mean)
        )

        return dNorth, dEast, dZ

    # ==================================================================
    # МЕТОД НАИМЕНЬШЕЙ КРИВИЗНЫ
    # ==================================================================

    def method_minimum_curvature(
        self,
        dl: float,
        azimuth_grid_start: float,
        azimuth_grid_end: float,
        zenith_start: float,
        zenith_end: float,
    ) -> tuple[float, float, float]:
        """
        Рассчитывает приращения методом наименьшей кривизны.
        """

        beta = self._calculate_beta(
            azimuth_grid_start,
            azimuth_grid_end,
            zenith_start,
            zenith_end,
        )

        # Для beta -> 0 RF -> 1.
        # Этот случай отдельно обрабатывается
        # в inclinometry_step().
        if isclose(beta, 0.0, abs_tol=1e-12):
            return self.method_mean_angle(
                dl,
                azimuth_grid_start,
                azimuth_grid_end,
                zenith_start,
                zenith_end,
            )

        ratio_factor = (
            2.0 / beta
        ) * tan(beta / 2.0)

        dNorth = (
            dl
            / 2.0
            * (
                sin(zenith_start)
                * cos(azimuth_grid_start)
                + sin(zenith_end)
                * cos(azimuth_grid_end)
            )
            * ratio_factor
        )

        dEast = (
            dl
            / 2.0
            * (
                sin(zenith_start)
                * sin(azimuth_grid_start)
                + sin(zenith_end)
                * sin(azimuth_grid_end)
            )
            * ratio_factor
        )

        dZ = (
            dl
            / 2.0
            * (
                cos(zenith_start)
                + cos(zenith_end)
            )
            * ratio_factor
        )

        return dNorth, dEast, dZ

    # ==================================================================
    # РАСЧЁТ ОДНОГО ИНТЕРВАЛА
    # ==================================================================

    def inclinometry_step(
        self,
        dl: float,
        azimuth_grid_start: float,
        azimuth_grid_end: float,
        zenith_start: float,
        zenith_end: float,
    ) -> tuple[float, float, float]:
        """
        Рассчитывает приращения координат одного интервала.

        Для нулевого угла β используется метод средних углов.
        В остальных случаях — метод наименьшей кривизны.

        Returns
        -------
        tuple[float, float, float]
            dNorth, dEast, dZ.
        """

        beta = self._calculate_beta(
            azimuth_grid_start,
            azimuth_grid_end,
            zenith_start,
            zenith_end,
        )

        if isclose(beta, 0.0, abs_tol=1e-12):
            return self.method_mean_angle(
                dl,
                azimuth_grid_start,
                azimuth_grid_end,
                zenith_start,
                zenith_end,
            )

        return self.method_minimum_curvature(
            dl,
            azimuth_grid_start,
            azimuth_grid_end,
            zenith_start,
            zenith_end,
        )

    # ==================================================================
    # ПОЛНЫЙ РАСЧЁТ ТРАЕКТОРИИ
    # ==================================================================

    def inclinometry(
        self,
        wellhead: tuple[float, float, float],
        measure: list[tuple[float, float, float]],
        err_l: float = 0.0,
        err_a: float = 0.0,
        err_i: float = 0.0,
    ) -> list[tuple[float, ...]]:
        """
        Рассчитывает основную траекторию и четыре крайних
        положения с учётом погрешностей.

        Parameters
        ----------
        wellhead : tuple[float, float, float]
            Координаты устья:
            (Север, Восток, Глубина).

        measure : list[tuple[float, float, float]]
            Измерения:
            (MD, дирекционный угол, зенитный угол).

        err_l : float
            Погрешность длины, м.

        err_a : float
            Погрешность азимута, радианы.

        err_i : float
            Погрешность зенитного угла, радианы.

        Returns
        -------
        list[tuple[float, ...]]
            Для каждой точки:
            
            0-2   — основной ствол;
            3-5   — верх;
            6-8   — лево;
            9-11  — низ;
            12-14 — право.
        """

        # Погрешность длины пока не используется
        # в существующей математической модели.
        _ = err_l

        if not measure:
            return []

        north, east, depth = wellhead

        result = [[
            north, east, depth,
            north, east, depth,
            north, east, depth,
            north, east, depth,
            north, east, depth,
        ]]

        for i in range(1, len(measure)):
            previous = measure[i - 1]
            current = measure[i]

            dl = current[0] - previous[0]

            # ----------------------------------------------------------
            # Основной ствол
            # ----------------------------------------------------------

            dNorth, dEast, dZ = self.inclinometry_step(
                dl,
                previous[1],
                current[1],
                previous[2],
                current[2],
            )

            # ----------------------------------------------------------
            # Верх
            # ----------------------------------------------------------

            dNorth_up, dEast_up, dZ_up = self.inclinometry_step(
                dl,
                previous[1],
                current[1],
                previous[2] + err_i,
                current[2] + err_i,
            )

            # ----------------------------------------------------------
            # Лево
            # ----------------------------------------------------------

            dNorth_left, dEast_left, dZ_left = self.inclinometry_step(
                dl,
                previous[1] - err_a,
                current[1] - err_a,
                previous[2],
                current[2],
            )

            # ----------------------------------------------------------
            # Низ
            # ----------------------------------------------------------

            dNorth_down, dEast_down, dZ_down = self.inclinometry_step(
                dl,
                previous[1],
                current[1],
                previous[2] - err_i,
                current[2] - err_i,
            )

            # ----------------------------------------------------------
            # Право
            # ----------------------------------------------------------

            dNorth_right, dEast_right, dZ_right = self.inclinometry_step(
                dl,
                previous[1] + err_a,
                current[1] + err_a,
                previous[2],
                current[2],
            )

            previous_result = result[-1]

            result.append((
                previous_result[0] + dNorth,
                previous_result[1] + dEast,
                previous_result[2] + dZ,

                previous_result[3] + dNorth_up,
                previous_result[4] + dEast_up,
                previous_result[5] + dZ_up,

                previous_result[6] + dNorth_left,
                previous_result[7] + dEast_left,
                previous_result[8] + dZ_left,

                previous_result[9] + dNorth_down,
                previous_result[10] + dEast_down,
                previous_result[11] + dZ_down,

                previous_result[12] + dNorth_right,
                previous_result[13] + dEast_right,
                previous_result[14] + dZ_right,
            ))

        return result

    # ==================================================================
    # ОБЛАСТЬ ОШИБКИ
    # ==================================================================

    @staticmethod
    def error_ellipse(
        l: float,
        err_a: float,
        err_i: float,
        err_m: float,
    ) -> tuple[float, float]:
        """
        Рассчитывает размеры области ошибки.

        Returns
        -------
        tuple[float, float]
            a — горизонтальный размер, м.
            b — вертикальный размер, м.
        """

        a = l * tan(
            abs(err_a) + abs(err_m)
        )

        b = l * tan(
            abs(err_i)
        )

        return a, b

    # ==================================================================
    # КРАЙНИЕ ТОЧКИ ОБЛАСТИ ОШИБКИ
    # ==================================================================

    @staticmethod
    def perpendicular_points(
        north1: float,
        east1: float,
        md1: float,
        north2: float,
        east2: float,
        md2: float,
        a: float,
        b: float,
        azimuth: float | None = None,
    ) -> list[float]:
        """
        Рассчитывает четыре крайние точки области ошибки.

        azimuth — дирекционный угол в радианах.
        """

        d_north = north2 - north1
        d_east = east2 - east1
        d_depth = md2 - md1

        horizontal_length = sqrt(
            d_north**2 + d_east**2
        )

        length = sqrt(
            d_north**2
            + d_east**2
            + d_depth**2
        )

        if isclose(length, 0.0, abs_tol=1e-12):
            raise ValueError(
                "Начальная и конечная точки совпадают."
            )

        # ----------------------------------------------------------
        # ВЕРТИКАЛЬНЫЙ УЧАСТОК
        # ----------------------------------------------------------

        if isclose(horizontal_length, 0.0, abs_tol=1e-12):
            if azimuth is None:
                azimuth = 0.0

            sin_az = sin(azimuth)
            cos_az = cos(azimuth)

            # LEFT
            north_left = north2 - a * sin_az
            east_left = east2 + a * cos_az
            md_left = md2

            # RIGHT
            north_right = north2 + a * sin_az
            east_right = east2 - a * cos_az
            md_right = md2

            # UP — горизонтальное смещение по азимуту
            north_up = north2 + b * cos_az
            east_up = east2 + b * sin_az
            md_up = md2

            # DOWN — противоположное смещение
            north_down = north2 - b * cos_az
            east_down = east2 - b * sin_az
            md_down = md2

            return [
                north_left, east_left, md_left,
                north_right, east_right, md_right,
                north_up, east_up, md_up,
                north_down, east_down, md_down,
            ]

        # ----------------------------------------------------------
        # ОБЫЧНЫЙ УЧАСТОК
        # ----------------------------------------------------------

        north_left = (
            north2 - a * d_east / horizontal_length
        )
        east_left = (
            east2 + a * d_north / horizontal_length
        )
        md_left = md2

        north_right = (
            north2 + a * d_east / horizontal_length
        )
        east_right = (
            east2 - a * d_north / horizontal_length
        )
        md_right = md2

        north_up = (
            north2
            - b * d_north * d_depth
            / (length * horizontal_length)
        )
        east_up = (
            east2
            - b * d_east * d_depth
            / (length * horizontal_length)
        )
        md_up = (
            md2 - b * horizontal_length / length
        )

        north_down = (
            north2
            + b * d_north * d_depth
            / (length * horizontal_length)
        )
        east_down = (
            east2
            + b * d_east * d_depth
            / (length * horizontal_length)
        )
        md_down = (
            md2 + b * horizontal_length / length
        )

        return [
            north_left, east_left, md_left,
            north_right, east_right, md_right,
            north_up, east_up, md_up,
            north_down, east_down, md_down,
        ]

    # ==================================================================
    # РАСЧЁТ КРАЙНИХ ТОЧЕК
    # ==================================================================

    def calculate_error_points(
        self,
        north1: float,
        east1: float,
        md1: float,
        north2: float,
        east2: float,
        md2: float,
        l: float,
        err_a: float,
        err_i: float,
        err_m: float,
        azimuth: float | None = None,
    ) -> tuple[float, float, list[float]]:

        a, b = self.error_ellipse(
            l,
            err_a,
            err_i,
            err_m,
        )

        points = self.perpendicular_points(
            north1,
            east1,
            md1,
            north2,
            east2,
            md2,
            a,
            b,
            azimuth,
        )

        return a, b, points