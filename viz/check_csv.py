import pandas as pd
df = pd.read_csv("cases.csv")
print(df.columns.tolist())
print(df.head(3))