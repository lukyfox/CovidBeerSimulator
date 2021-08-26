import pandas as pd
import plotly.graph_objects as go
import os

def final_vizualizer(df_datastore, max_steps):
    """

    :param df_datastore:
    :param max_steps:
    :return:
    """
    reference = df_datastore.loc[df_datastore['precautions']=='no_covid'].index
    beer_reference = df_datastore.loc[reference, 'beer_lahvove'] + df_datastore.loc[reference, 'beer_cepovane']
    eval_reference = df_datastore.loc[reference, 'scenario_rating']

    for i, scenario in enumerate(df_datastore.itertuples()):
        beer_eval = int(((scenario.beer_lahvove + scenario.beer_cepovane)/beer_reference.values[0])*100)
        eval_eval = int((scenario.scenario_rating/eval_reference.values[0])*100)
        df_datastore.loc[scenario.Index, 'precautions'] = f'{scenario.precautions} ({eval_eval}%|{beer_eval}%)'

    fig = go.Figure(data=[
        go.Bar(name='Lahvove', x=df_datastore['precautions'], y=df_datastore['beer_lahvove'],
               text=df_datastore['beer_lahvove'].round(0).astype(int)),
        go.Bar(name='Cepovane', x=df_datastore['precautions'], y=df_datastore['beer_cepovane'],
               text=df_datastore['beer_cepovane'].round(0).astype(int)),
        go.Scatter(name='Hodnoceni scenare', x=df_datastore['precautions'], y=df_datastore['scenario_rating'],
                   text=df_datastore['scenario_rating']),
        go.Scatter(name='Infikovani (x10 zoom)', x=df_datastore['precautions'], y=df_datastore['epi_infected']*10,
                   text=df_datastore['epi_infected'], hovertext=df_datastore['epi_infected'])
    ])
    fig.update_layout(barmode='stack', #template='plotly_dark',
                      #legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="right", x=1)
                      )



    fig.show()
    #path = os.path.join(os.path.join(os.getcwd(), 'data/results/{}_final_results.html'.format(max_steps)))
    #fig.write_html(path)

df = pd.read_csv('data/results/2400_simple_final_results.csv', sep=';')
#df['scenario_rating'] = df['beer_cepovane'] + df['beer_lahvove'] - 10*df['epi_infected'] - 1000*df['epi_death_agents']
df.sort_values(['scenario_rating'], inplace=True)
final_vizualizer(df, 2400)

df = pd.read_csv('data/results/2400_combi_final_results.csv', sep=';')
#df['scenario_rating'] = df['beer_cepovane'] + df['beer_lahvove'] - 10*df['epi_infected'] - 1000*df['epi_death_agents']
df.sort_values(['scenario_rating'], inplace=True)
final_vizualizer(df, 2400)