import os
import sys
import sqlite3
import time
import json
import pandas as pd
import message_converter
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from tqdm import tqdm

class BagConverter:
    def __init__(self):
        self.cursor = None
        self.conn = None
        self.bag_file_path = None

    def connectDB(self, dirname):
        bagfile_name = dirname.split("/")[-1]
        bag_file_path = dirname + "/" + bagfile_name + "_0" + ".db3"
        if not os.path.exists(bag_file_path):
            print(f"Bag file not found: {bag_file_path}")
            return

        self.bag_file_path = bag_file_path
        self.conn = sqlite3.connect(bag_file_path)
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
        return os.path.join(os.path.dirname(self.bag_file_path), filename)

    def loadCache(self, topic_name, ext="feather"):
        path = self._get_topic_cache_path(topic_name, ext)
        if not os.path.exists(path):
            return None

        if ext == "feather":
            return pd.read_feather(path)
        elif ext == "csv":
            return pd.read_csv(path)
        else:
            raise ValueError("Unsupported cache extension")

    def saveCache(self, data, ext="feather"):
        save_dir = os.path.dirname(self.bag_file_path)

        for topic_name, records in data.items():
            filename = self._sanitize_topic_name(topic_name) + f".{ext}"
            path = os.path.join(save_dir, filename)

            if ext == "feather":
                df = pd.DataFrame(records)
                df.to_feather(path)
            elif ext == "csv":
                df = pd.DataFrame(records)
                df.to_csv(path, index=False)
            else:
                raise ValueError("Unsupported cache extension")

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
            print(f"[INFO] Deserializing topic: {topicName} ({len(messageRecords)} messages)")
            for _, _, timeStamps, rowDatas in tqdm(messageRecords, desc=f"  Progress [{topicName}]", unit="msg"):
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
        if self.bag_file_path is None:
            print("Please connect to bag DB first via connectDB()")
            return None

        if use_cache:
            cached_df = self.loadCache(topic_name, cache_ext)
            if cached_df is not None:
                print(f"[INFO] Loaded cache for topic '{topic_name}' from {self._get_topic_cache_path(topic_name, cache_ext)}")
                return cached_df

        topicDict = self._extractDataFromDB()
        self._closeDB()

        if topic_name not in topicDict:
            print(f"[ERROR] Topic '{topic_name}' not found in bag")
            sys.exit(1)

        self.saveCache(topicDict, cache_ext)
        df = pd.DataFrame(topicDict[topic_name])
        return df
