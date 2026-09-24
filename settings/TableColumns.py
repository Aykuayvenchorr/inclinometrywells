# Словари для всех таблиц в проекте (не думаю что их нужно разделять на несколько классов
# так как их немного и вряд ли их будет много в будующем)

class TableColumns:

    inclinometry = {
        "MD": 0,
        "ZENITH": 1,
        "AZIMUTH": 2,
        "DATE": 3,
        "NORTH": 4,
        "EAST": 5,
        "TVDSS": 6,
        "CONVERGENCE": 7,
        "DECLINATION": 8,
        "GRID_AZIMUTH": 9,
        "DELTA_NORTH": 10,
        "DELTA_EAST": 11,
        "DELTA_TVDSS": 12,
        "NORTH_TOP": 13,
        "EAST_TOP": 14,
        "TVDSS_TOP": 15,
        "NORTH_LEFT": 16,
        "EAST_LEFT": 17,
        "TVDSS_LEFT": 18,
        "NORTH_DOWN": 19,
        "EAST_DOWN": 20,
        "TVDSS_DOWN": 21,
        "NORTH_RIGHT": 22,
        "EAST_RIGHT": 23,
        "TVDSS_RIGHT": 24,
        "a": 25,
        "b": 26

    }

    targets = {
        "ID": 0,
        "NORTH": 1,
        "EAST": 2,
        "TVDSS": 3,
    }

