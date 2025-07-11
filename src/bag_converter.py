import os
import sys
import sqlite3
import time
import json
import pandas as pd
import message_converter
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


class BagConverter:
    def __init__(self):
        self.cursor = None
        self.conn = None
        self.bag_file = None

    def connectDB(self, bag_file):
        if not os.path.exists(bag_file):
            print(f"Bag file not found: {bag_file}")
            return

        self.bag_file = bag_file
        self.conn = sqlite3.connect(bag_file)
        self.cursor = self.conn.cursor()

    def _closeDB(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
            self.cursor = None

    def __flatten_dict(self, d, parent_key='', sep='/'):
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
        return "{}.{}".format(
            time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(timeStamps / 1_000_000_000)),
            timeStamps % 1_000_000_000,
        )

    def _calcMilliSeconds(self, timeStamps, zeroIndexTimeStamp):
        return (timeStamps - zeroIndexTimeStamp) / 1_000_000

    def _sanitize_topic_name(self, topic_name):
        return topic_name.strip("/").replace("/", "_")

    def _get_topic_cache_path(self, topic_name, ext):
        filename = self._sanitize_topic_name(topic_name) + f".{ext}"
        return os.path.join(os.path.dirname(self.bag_file), filename)

    def loadCache(self, topic_name, ext="feather"):
        path = self._get_topic_cache_path(topic_name, ext)
        if not os.path.exists(path):
            return None

        if ext == "feather":
            return pd.read_feather(path)
        elif ext == "json":
            with open(path, "r") as f:
                return json.load(f)
        else:
            raise ValueError("Unsupported cache extension")

    def saveCache(self, data, ext="feather"):
        """
        トピックごとに feather, json, csv で個別保存
        - 保存先: bagファイルと同じフォルダ
        - ファイル名: トピック名を整形して使用（例: /sg/pressure → pressure.feather, pressure.csv）
        """
        save_dir = os.path.dirname(self.bag_file)
    
        for topic_name, records in data.items():
            base_filename = self._sanitize_topic_name(topic_name)
            df = pd.DataFrame(records)
    
            if ext == "feather" or ext == "all":
                feather_path = os.path.join(save_dir, base_filename + ".feather")
                df.to_feather(feather_path)
                print(f"[INFO] Saved feather to {feather_path}")
    
            if ext == "csv" or ext == "all":
                csv_path = os.path.join(save_dir, base_filename + ".csv")
                df.to_csv(csv_path, index=False)
                print(f"[INFO] Saved CSV to {csv_path}")
    
            if ext == "json" or ext == "all":
                json_path = os.path.join(save_dir, base_filename + ".json")
                with open(json_path, "w") as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
                print(f"[INFO] Saved JSON to {json_path}")

    def _extractDataFromDB(self):
        topicDict = {}

        self.cursor.execute('SELECT id, name, type FROM topics')
        topicRecords = self.cursor.fetchall()

        for topicID, topicName, topicType in topicRecords:
            topicTypeClassName = get_message(topicType)

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

                    _tmpDict = {
                        'row_time': self._calcDataTime(timeStamps),
                        'msec': self._calcMilliSeconds(timeStamps, zeroIndexTimeStamp),
                    }
                    _tmpDict.update(flattenDict)
                    dataList.append(_tmpDict)
                except Exception as e:
                    print(f"[WARN] Failed to deserialize message on topic '{topicName}': {e}")
                    continue

            topicDict[str(topicName)] = dataList

        return topicDict

    def getAllTopicNameAndMessageType(self):
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
                    
    def getTopicDataWithPandas(self, topic_name, use_cache=True, cache_ext="feather"):
        if self.bag_file is None:
            print("Please connect to bag DB first via connectDB()")
            return None
    
        if use_cache:
            cached_df = self.loadCache(topic_name, cache_ext)
            if cached_df is not None:
                print(f"[INFO] Loaded cache for topic '{topic_name}' from {self._get_topic_cache_path(topic_name, cache_ext)}")
                return cached_df
    
        self.connectDB(self.bag_file)
        topicDict = self._extractDataFromDB()
        self._closeDB()
    
        if topic_name not in topicDict:
            print(f"[ERROR] Topic '{topic_name}' not found in bag")
            sys.exit(1)
    
        # キャッシュ保存を有効化
        self.saveCache({topic_name: topicDict[topic_name]}, ext=cache_ext)
    
        df = pd.DataFrame(topicDict[topic_name])
        return df
