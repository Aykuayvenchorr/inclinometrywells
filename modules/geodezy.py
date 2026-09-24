from math import atan, sin, cos, sqrt, atan2, radians, acos, asin, tan, degrees
from . import ppigrf
from datetime import date, datetime
import numpy as np


class Geodezy:
    """
    Геодезические расчеты
    """
    def __init__(self):
        pass

    @staticmethod
    def getPulkovo1942EllipsoidParameters():
        """
        Возвращает параметры эллипсоида Пулково 1942

        Returns
        -------
        a : float
            Большая полуось эллипсоида, м
        b : float
            Малая полуось эллипсоида, м
        """
        a = 6378245.0  # Большая полуось эллипсоида, м
        b = 6356863.0188  # Малая полуось эллипсоида, м
        return a, b

    @staticmethod
    def getProjectionType(crs):
        if not crs.isValid():
            return None

        proj = crs.toProj()

        if "+proj=utm" in proj:
            return "utm"

        if "+proj=tmerc" in proj:
            if "+k=1" in proj or "+k_0=1" in proj or "+k=0.9996" in proj:
                return "gauss_kruger"

        return None

    @staticmethod
    def getCentralMeridian_(crs) -> float:
        projection_type = Geodezy.getProjectionType(crs)

        if projection_type == "utm":
            proj = crs.toProj()

            zone = int(proj.split("+zone=")[1].split()[0])
            longitude_deg = zone * 6 - 183
            # print(f"Central meridian (degrees): {longitude_deg}")
            return Geodezy.deg2rad(longitude_deg)

        if projection_type == "gauss_kruger":
            proj = crs.toProj()
            longitude_deg = float(proj.split("+lon_0=")[1].split()[0])
            # print(f"Central meridian (degrees): {longitude_deg}")
            return Geodezy.deg2rad(longitude_deg)

        return None

    @staticmethod
    def getCentralMeridian(zone_number: int) -> float:
        """
        Возвращает долготу осевого меридиана зоны в радианах

        Parameters
        ----------
        zone_number : int
            Номер зоны (1-60)

        Returns
        -------
        float
            Долгота осевого меридиана зоны, радианы
        """
        if zone_number < 1 or zone_number > 60:
            raise ValueError("Номер зоны должен быть в диапазоне от 1 до 60.")
        
        # Долгота осевого меридиана зоны в градусах
        lon0_deg = (zone_number * 6) - 3
        # Переводим в радианы
        lon0_rad = radians(lon0_deg)

        return lon0_rad

    @staticmethod
    def getZoneNumberFromEast(east: float) -> int:
        """
        Возвращает номер зоны по прямоугольной координате восток (метры) с зоной

        Parameters
        ----------
        east : float
            Восточная координата точки с зоной, метры

        Returns
        -------
        int
            Номер зоны (1-60)
        """
        zone_number = int(east // 1000000)
        return zone_number

    @staticmethod
    def getZoneNumberFromLongitude(longitude: float) -> int:
        """
        Возвращает номер зоны по географической долготе (градусы)

        Parameters
        ----------
        longitude : float
            Географическая долгота точки, градусы

        Returns
        -------
        int
            Номер зоны (1-60)
        """
        zone_number = int((longitude + 180) // 6) + 1
        return zone_number

    @staticmethod
    def convergence_meridians(B: float, L: float, central_meridian: float, projection_type, rel: int) -> float:
        """
        Расчет сближения меридианов по формуле Морозова.

        Параметры
        ----------
        B : float
            Геодезическая широта, радианы    
        L : float
            Геодезическая долгота точки, радианы    
        zone : int
            Номер зоны (1-60)

        Возвращает
        ----------
        float
            Сближение меридианов, радианы
        """
        if rel <= 1:
            # -----------------------------------------
            # Выбор эллипсоида
            # -----------------------------------------
            if projection_type == "utm":
                # UTM → WGS84
                a = 6378137.0
                b = 6356752.314245

            elif projection_type == "gauss_kruger":
                # Гаусс-Крюгер → Пулково-1942
                a, b = Geodezy.getPulkovo1942EllipsoidParameters()

            # a, b = Geodezy.getPulkovo1942EllipsoidParameters()
            # L0 = Geodezy.getCentralMeridian(zone)
            L0 = central_meridian

            # Разность долгот
            l = L - L0

            # Первый эксцентриситет²
            #e2 = (a**2 - b**2) / (a**2)
            # Второй эксцентриситет²
            es2 = (a**2 - b**2) / (b**2)
            # η²
            eta2 = es2 * cos(B) ** 2

            # Формула Морозова
            tg_gamma = (sin(B) * tan(l) + (eta2 * sin(B) * cos(B)**2 * l**3* (1 + (2/3)*eta2 + cos(B)**2 * l**2)))
            gamma = atan(tg_gamma)
            return gamma
        else:
            return 0.0

    @staticmethod
    def azimuth_true_2_grid(azimuth_true: float, convergence_meridians: float) -> float:
        """
        Расчет дирекционного угла по истинному азимуту и сближению меридианов

        Параметры
        ----------
        azimuth_true : float
            Истинный азимут, радианы
        convergence_meridians : float
            Сближение меридианов, радианы
        lon0_deg : float
            Долгота осевого меридиана зоны, радианы
        
        Возвращает
        ----------
        float
            Дирекционный угол, радианы
        """
        # Дирекционный угол
        azimuth_grid = azimuth_true + convergence_meridians

        return azimuth_grid
    
    @staticmethod
    def magnetic_declination(lat_rad: float, lon_rad: float, alt_km: float, dt: datetime, rel: int) -> float:
        """
        Расчет магнитного склонения по модели IGRF.

        Параметры
        ----------
        lat_rad : float
            Геодезическая широта, радианы
        lon_rad : float
            Геодезическая долгота точки, радианы
        alt_m : float
            Альтитуда точки, м
        dt : datetime
            Дата
        
        Возвращает
        ----------
        float
            Магнитное склонение, радианы
        """

        if rel == 0:
            # Переводим радианы в градусы для IGRF
            lat_deg = degrees(lat_rad)
            lon_deg = degrees(lon_rad)
            # Расчет компонентов напряженности магнитного поля Восток, Север, Нормальное (вверх)
            Be, Bn, Bu = ppigrf.igrf(lon=lon_deg, lat=lat_deg, h=alt_km, date=dt)

            # Полная напряженность
            total = np.sqrt(Bn**2 + Be**2 + Bu**2)

            # Магнитное склонение (в радианах)
            declination_rad = np.arctan2(Be, Bn)    # arctan2(Восток, Север)
            declination_deg = np.degrees(declination_rad)

            # Магнитное наклонение
            horizontal = np.sqrt(Bn**2 + Be**2)
            inclination_rad = np.arctan2(Bu, horizontal)
            inclination_deg = np.degrees(inclination_rad)

            # Вычисление изменения магнитного склонения в год
            date_old = datetime(dt.year - 1, dt.month, dt.day)
            Be_old, Bn_old, Bu_old = ppigrf.igrf(lon=lon_deg, lat=lat_deg, h=alt_km, date=date_old)
            declination_rad_old = np.arctan2(Be_old, Bn_old)
            declination_deg_old = np.degrees(declination_rad_old)
            change_per_year = declination_deg_old - declination_deg
            # print(f'Широта: {lat_deg:.7f} / Долгота: {lon_deg:.7f} / Дата: {dt} / Альтитуда: {alt_km:.7f} / Магсклон: {declination_deg}')
        else:
            declination_rad = 0.0
            change_per_year = 0.0

        return declination_rad

    @staticmethod
    def rad2deg(rad: float) -> float:
        """
        Перевод радиан в градусы

        Parameters
        ----------
        rad : float
            Угол в радианах

        Returns
        -------
        float
            Угол в градусах
        """
        return degrees(rad)

    @staticmethod
    def deg2rad(deg: float) -> float:
        """
        Перевод градусов в радианы

        Parameters
        ----------
        deg : float
            Угол в градусах

        Returns
        -------
        float
            Угол в радианах
        """
        return radians(deg)