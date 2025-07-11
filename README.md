bagファイルのデータを取り出して，pandasのデータフレーム型で取りだすユーティリティです．

# set up

docker composeでjupyter labの仮想環境を立ち上げる。どちらか一つを選択します

-  簡単に実行する場合
```
docker compose up jupyter
```

- gpuの実行環境が整っている場合
```
docker compose up jupyter_gpu
```

gpuのset_upの方法はnotionページ参照

[nvidia driverのインストール](https://www.notion.so/Jupyter-Lab-c7c0895e101b464c94d23811da65e479)

- portを指定したい場合(例:7000番)は以下のとおり
```
PORT=7000 docker compose up jupyter
```

# how to use

```converter.py
# bag_converterクラスをインポート
import bag_converter

# bag_fileには記録したバグファイルを指定してください
bag_converter.connectDB(bag_file)
# .bagファイルから"/topicname"で指定したバグデータを取得
#　dfで取り出される．
df = bag_converter.getTopicDataWithPandas("/topicname")
bag_converter.closeDB()
```

# 問題,今後の改良
.devcontainerで作業をしようとするとpathのインクルードがうまくいきません。
- /workspaceを作業フォルダに指定していますが、実行時に$PYTHONPATH環境変数に追加されないため、sys.append.path("/workspace")のように指定する必要があるます。
- path="/bag/..."のようにbagファイルを指定しても動きません。path="/workspace/bag..."のように指定する必要があります。


# refer from
https://github.com/fishros/ros2bag_convert
