import os
import sys
import sqlite3
import message_converter
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
import pandas as pd
import time

class BagConverter:
    def __init__(self):
        self.cursor = None
        self.conn = None
        self.bag_file = None
        self.topic_data_cache = None  # 全トピックデータ辞書キャッシュ

    def connectDB(self, bag_file):
        """ bagファイルのSQLite DBに接続 """
        if not os.path.exists(bag_file):
            print(f"Bag file not found: {bag_file}")
            return

        self.bag_file = bag_file
        self.conn = sqlite3.connect(bag_file)
        self.cursor = self.conn.cursor()

    def _closeDB(self):
        """ DB接続を閉じる """
        if self.conn is not None:
            self.conn.close()
            self.conn = None
            self.cursor = None

    def __flatten_dict(self, d, parent_key='', sep='/'):
        """
        ネストされた辞書をフラット化。リストはindex付きキーに展開。
        """
        items = []
        i = 0
        for key, val in d.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            if isinstance(val, dict):
                items.extend(self.__flatten_dict(val, new_key, sep=sep).items())
            elif isinstance(val, list):
                for val_i in val:
                    items.append((new_key + '/' + str(i), val_i))
                    i += 1
            else:
                items.append((new_key, val))
            i = 0
        return dict(items)

    def _calcDataTime(self, timeStamps):
        """ タイムスタンプから人間が読める文字列を作成 """
        row_time = "{}.{}".format(
            time.strftime(
                "%Y/%m/%d %H:%M:%S", time.localtime(timeStamps / 1_000_000_000)
            ),
            timeStamps % 1_000_000_000,
        )
        return row_time

    def _calcMilliSeconds(self, timeStamps, zeroIndexTimeStamp):
        """ 最初のタイムスタンプとの差をミリ秒で返す """
        return (timeStamps - zeroIndexTimeStamp) / 1_000_000

    def _extractDataFromDB(self):
        """
        bag DBから全トピックのメッセージを読み込む。
        辞書形式で返す {topicName: [dict, dict, ...], ...}
        """
        topicDict = {}

        # トピック情報取得
        self.cursor.execute('SELECT id, name, type FROM topics')
        topicRecords = self.cursor.fetchall()

        for topicID, topicName, topicType in topicRecords:
            topicTypeClassName = get_message(topicType)

            # メッセージ取得
            self.cursor.execute(
                'SELECT id, topic_id, timestamp, data FROM messages WHERE topic_id = ?',
                (topicID,)
            )
            messageRecords = self.cursor.fetchall()

            if not messageRecords:
                continue

            zeroIndexTimeStamp = messageRecords[0][2]

            dataList = []
            for _, _, timeStamps, rowDatas in messageRecords:
                try:
                    deserialized = deserialize_message(rowDatas, topicTypeClassName)
                    rowDataDic = message_converter.convert_ros_message_to_dictionary(deserialized)
                    flattenDict = self.__flatten_dict(rowDataDic)

                    # 時刻情報追加
                    _tmpDict = {
                        'row_time': self._calcDataTime(timeStamps),
                        'msec': self._calcMilliSeconds(timeStamps, zeroIndexTimeStamp),
                    }
                    _tmpDict.update(flattenDict)
                    dataList.append(_tmpDict)

                except Exception:
                    # デシリアライズ失敗は無視
                    continue

            topicDict[str(topicName)] = dataList

        return topicDict

    def getAllTopicNameAndMessageType(self):
        """ 全トピック名と、先頭メッセージのフラットキー一覧を表示 """
        self.cursor.execute('SELECT name, id, type FROM topics')
        records = self.cursor.fetchall()
        if not records:
            print("No topics found")
            return

        for topic_name, topicID, topicType in records:
            topicTypeClassName = get_message(topicType)
            self.cursor.execute('SELECT data FROM messages WHERE topic_id = ? LIMIT 1', (topicID,))
            row = self.cursor.fetchone()
            if not row:
                print(f"{topic_name}: No message data found")
                continue

            rowDatas = row[0]
            deserialized = deserialize_message(rowDatas, topicTypeClassName)
            rowDataDic = message_converter.convert_ros_message_to_dictionary(deserialized)
            flattenDict = self.__flatten_dict(rowDataDic)

            print(f"{topic_name}:")
            for key in flattenDict.keys():
                print(f"  - {key}")

    def _get_cache_path(self, ext="feather"):
        """
        bagファイルと同じディレクトリに、
        <bagbasename>.<ext> をキャッシュファイル名として返す
        """
        dir_path = os.path.dirname(self.bag_file)
        base_name = os.path.splitext(os.path.basename(self.bag_file))[0]
        return os.path.join(dir_path, f"{base_name}.{ext}")

    def loadCache(self, ext="feather"):
        """ キャッシュファイルを読み込み（存在しなければNone返す） """
        cache_path = self._get_cache_path(ext)
        if not os.path.exists(cache_path):
            return None

        if ext == "feather":
            return pd.read_feather(cache_path)
        elif ext == "json":
            import json
            with open(cache_path, "r") as f:
                return json.load(f)
        else:
            raise ValueError("Unsupported cache extension")

    def saveCache(self, data, ext="feather"):
        """ キャッシュファイルを書き込み """
        cache_path = self._get_cache_path(ext)
        if ext == "feather":
            # featherはpandas.DataFrame限定なのでdataをDataFrameに変換して保存
            df = pd.DataFrame(data)
            df.to_feather(cache_path)
        elif ext == "json":
            import json
            with open(cache_path, "w") as f:
                json.dump(data, f)
        else:
            raise ValueError("Unsupported cache extension")

    def getTopicDataWithPandas(self, topicName, use_cache=True, cache_ext="feather"):
        """
        指定トピックのDataFrameを取得。

        - use_cache=Trueならキャッシュから読み込みを試みる
        - なければDBから読み込みキャッシュ保存する

        返り値はpandas.DataFrame
        """
        if self.bag_file is None:
            print("Please connect to bag DB first via connectDB()")
            return None

        if use_cache:
            cached_df = self.loadCache(cache_ext)
            if cached_df is not None:
                if topicName in cached_df.columns:
                    # featherの場合はカラムがフラットなので全体DataFrameを返すが
                    # 列フィルターは呼び出し側で対応推奨
                    print(f"Loaded cached data from {self._get_cache_path(cache_ext)}")
                    return cached_df
                elif isinstance(cached_df, dict) and topicName in cached_df.keys():
                    # jsonロードの場合は辞書なので対応
                    print(f"Loaded cached data from {self._get_cache_path(cache_ext)}")
                    df = pd.DataFrame(cached_df[topicName])
                    return df
                else:
                    print("Cached data exists but topic not found, reloading from DB")

        # キャッシュなし or トピックなしの場合はDBから読み込み
        self.connectDB(self.bag_file)
        topicDict = self._extractDataFromDB()
        self._closeDB()

        if topicName not in topicDict:
            print(f"Topic '{topicName}' not found in bag")
            sys.exit(1)

        # キャッシュ保存（全トピックを一括保存）
        self.saveCache(topicDict, cache_ext)

        # 返すのは指定トピックのDataFrame
        df = pd.DataFrame(topicDict[topicName])
        return df
