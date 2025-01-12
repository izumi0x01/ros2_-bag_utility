import os
import sqlite3
import message_converter
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rclpy.serialization import deserialize_message
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

    def closeDB(self):
        if self.conn is not None:
            self.conn.close()

    def __flatten_dict(self, d, parent_key='', sep='_'):
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
                    items.append((new_key + '_' + str(i), val_i))
                    i += 1
            else:
                items.append((new_key, val))
            i = 0
        return dict(items) 
    
    def _extractDataFromDB(self):

        self.cursor.execute('SELECT * from({})'.format('topics'))
        topicRecords = self.cursor.fetchall()
        self.cursor.execute('SELECT * from({})'.format('messages'))
        messageRecords = self.cursor.fetchall()
        
        topicDict = {}
        for topic_row in topicRecords:    
            topicID = topic_row[0]
            topicName = topic_row[1]
            topicType = topic_row[2]


            dataList = []
            for message_row in messageRecords:
                topicTypeClassName = get_message(topicType)
                rowDatas = message_row[3]
                messageID = message_row[1]
                timeStamps = message_row[2]
                
                if messageID != topicID:
                    continue

                try:
                  deserializedRowData = deserialize_message(rowDatas, topicTypeClassName)
                  rowDataDic = message_converter.convert_ros_message_to_dictionary(deserializedRowData)
                  flattenDict = self.__flatten_dict(rowDataDic)
                  _tmpDict = {}
                  _tmpDict['row_time'] = self._calcDataTime(timeStamps)
                  _tmpDict['msec'] = self._calcMilliSeconds(timeStamps, messageRecords[0][2])
                  _tmpDict.update(flattenDict)
                  dataList.append(_tmpDict)

                except Exception as e:
                  continue  

            _topicName = str(topicName)
            topicDict[_topicName] =  dataList

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
        

    def getTopicDataWithPandas(self, topicName):
        topicDict = self._extractDataFromDB()
        if topicName in topicDict.keys():
            df = pd.DataFrame(topicDict[topicName])
            return df
        else:
            print("Topic not found")
            exit(1)


