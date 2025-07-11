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

    def connectDB(self, bag_file):
        if not os.path.exists(bag_file):
            print("Bag file not found")
            return

        self.conn = sqlite3.connect(bag_file)
        self.cursor = self.conn.cursor()

    def _closeDB(self):
        if self.conn is not None:
            self.conn.close()

    def __flatten_dict(self, d, parent_key='', sep='/'):
        """
        unfold sub-structs, except struct array
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
    
    def _extractDataFromDB(self):
        topicDict = {}

        # Prepare topics
        self.cursor.execute('SELECT id, name, type FROM topics')
        topicRecords = self.cursor.fetchall()

        for topicID, topicName, topicType in topicRecords:
            topicTypeClassName = get_message(topicType)  # ✅ 外に出す

            # ✅ SQL で絞る
            self.cursor.execute('SELECT id, topic_id, timestamp, data FROM messages WHERE topic_id = ?', (topicID,))
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
                    continue

            topicDict[str(topicName)] = dataList
        return topicDict
    
    def _calcDataTime(self, timeStamps):
        row_time = "{}.{}".format(
            time.strftime(
                "%Y/%m/%d %H:%M:%S", time.localtime(timeStamps / 1000 / 1000 / 1000)
            ),
            timeStamps % (1000 * 1000 * 1000),
        )
        return row_time
    
    def _calcMilliSeconds(self, timeStamps, zeroIndexTimeStamp):
        return (timeStamps - zeroIndexTimeStamp) / 1000000
        

    def getAllTopicNameAndMessageType(self):
        """
        DB に含まれるすべてのトピックについて、
        最初の 1 件目の message の flatten keys を表示する
        """
        # すべての topic 名取得
        self.cursor.execute('SELECT name, id, type FROM topics')
        records = self.cursor.fetchall()
        if not records:
            print("No topics found")
            return

        for topic_name, topicID, topicType in records:
            topicTypeClassName = get_message(topicType)

            # 先頭 1 件
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


    
    def getTopicDataWithPandas(self, topicName):
        topicDict = self._extractDataFromDB()
        if topicName in topicDict.keys():
            df = pd.DataFrame(topicDict[topicName])
            return df
        else:
            print("Topic not found")
            sys.exit(1)
        self._closeDB()


