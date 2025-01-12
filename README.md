bagファイルのデータを取り出して，pandasのデータフレーム型で取りだすユーティリティです．

# requirement

1. ローカルに直接colconの実行環境を作成する。
2. 環境を汚したくない場合は.devcontainerで実行してください。

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
