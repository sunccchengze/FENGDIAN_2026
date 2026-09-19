import numpy as np
normal_list = [1,2,3,4,5]

arr = np.array(normal_list)

print("×2:",arr*2)
print("加10：", arr + 10)       # [11, 12, 13, 14, 15]
print("平方：", arr ** 2)       # [1, 4, 9, 16, 25]

# ===== 第二件事：生成数组 =====
# linspace：在两个数之间均匀生成N个点
x = np.linspace(0, 1000, 128)   # 0到1000，生成128个点
print("x的长度：", len(x))      # 128
print("第一个：", x[0])         # 0.0
print("最后一个：", x[-1])      # 1000.0

y = np.linspace(-300, 300, 64)  # -300到300，生成64个点
print("y的长度：", len(y))      # 64

# ===== 第三件事：二维数组 =====
# 你的流场数据就是二维数组：64行 × 128列
u = np.zeros((64, 128))         # 全是0的二维数组
print("u的形状：", u.shape)     # (64, 128)
print("行数：", u.shape[0])     # 64
print("列数：", u.shape[1])     # 128