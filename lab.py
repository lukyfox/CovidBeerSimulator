import pandas as pd
import plotly.express as px


df_datastore = pd.read_csv(r'D:\FIM\_StZZ\data\DP\out\results\_res_complete.csv', sep=';')
#fig = px.bar(df_datastore, x="precautions", y=['beercon_cepovane', 'beercon_lahvove'], labels={
#    "beercon_lahvove": "Lahvove [l]",
#    "beercon_cepovane": "Cepovane [l]"
#},#text=['beercon_cepovane', 'beercon_lahvove'],
#              title="Pivni vysledky scenaru", barmode="stack")
#fig.update_layout(template='plotly_dark', legend=dict(
#    orientation="h", yanchor="bottom", y=-0.25, xanchor="right", x=1, ))

import plotly.graph_objects as go
fig = go.Figure(data=[
    go.Bar(name='Lahvove', x=df_datastore['precautions'], y=df_datastore['beercon_lahvove'],
           text=df_datastore['beercon_lahvove']),
    go.Bar(name='Cepovane', x=df_datastore['precautions'], y=df_datastore['beercon_cepovane'],
           text=df_datastore['beercon_cepovane']),
    go.Scatter(name='Infikovani (x10 zoom)', x=df_datastore['precautions'], y=df_datastore['epi_infected']*10,
               text=df_datastore['epi_infected'], hovertext=df_datastore['epi_infected'])
])
fig.update_layout(barmode='stack', template='plotly_dark',
                  legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="right", x=1))
fig.show()
