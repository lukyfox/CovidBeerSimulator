import pandas as pd

df = pd.DataFrame({'a': [10,20,30], 'b': ['10','20','30']})
mask = (df['a']>10)

df.loc[df.loc[mask].sample(1).index, 'b'] = 'changed'
print(df)
#df2 = df.loc[df['a']>20]