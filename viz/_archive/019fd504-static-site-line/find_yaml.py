import floris
import os

# 找到floris的安装位置
floris_path = os.path.dirname(floris.__file__)
print("FLORIS安装在：", floris_path)

# 在里面搜索gch.yaml
for root, dirs, files in os.walk(floris_path):
    for file in files:
        if file.endswith(".yaml"):
            print(os.path.join(root, file))