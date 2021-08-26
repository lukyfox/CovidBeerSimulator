
import os
import pandas as pd
import plotly.graph_objects as go
from mesa.batchrunner import BatchRunnerMP
from BeerModel import BeerModel

def get_beer_results(model):
    """

    :param model:
    :return:
    """
    # pri multiprocessingu musim uvest identifikaci scenare, vypis neni hned pod informaci o startu scenare
    print("*"*25,'\n',f'Scenario resuts for {model.simtype}: {",".join([p["name"]+"(tt:"+str(p["trigger_threshold"])+")" for p in model.applied_precautions])}', sep='')
    print(f"Beer consumed: {round(model.df_results.tail(1)['beer_consumption_sum_cepovane'].values[0],2)} l",
          f"cepovane, {round(model.df_results.tail(1)['beer_consumption_sum_lahvove'].values[0],2)} l lahvove")
    return {
        'cepovane': round(model.df_results.tail(1)['beer_consumption_sum_cepovane'].values[0], 2),
        'lahvove': round(model.df_results.tail(1)['beer_consumption_sum_lahvove'].values[0], 2)
    }

def get_epidemic_results(model):
    """

    :param model:
    :return:
    """
    if not model.df_infected_agents.empty:
        print('Agents infected during simulation (1st infection):', model.df_infected_agents['victim_id'].unique().shape[0])
        print('Plain attempts to infect others:', model.df_results['a_plain_infection_attempts'].sum())
        print('Successful attempts to infect others:', model.df_results['a_new_infections'].sum())
        print('Death agents:', model.df_results['death_agents'].max())
        return {#'typ': model.simtype,
            'infected': model.df_infected_agents['victim_id'].unique().shape[0],
            'plain_attempts': model.df_results['a_plain_infection_attempts'].sum(),
            'successful_attempts': model.df_results['a_new_infections'].sum(),
            'death_agents': model.df_results['death_agents'].max()}
    else:
        print('No infection - all agents kept healthy')
        return {#'typ': model.simtype,
            'infected': 0,
            'plain_attempts': 0,
            'successful_attempts': 0,
            'death_agents': 0}

def get_sim_duration(model):
    """

    :param model:
    :return:
    """
    duration = round(model.df_results['step_duration'].sum(), 0)
    print(f'Simulation performed all actions in {duration} s')
    return duration

def final_vizualizer(df_datastore, max_steps):
    """

    :param df_datastore:
    :param max_steps:
    :return:
    """
    fig = go.Figure(data=[
        go.Bar(name='Lahvove', x=df_datastore['precautions'], y=df_datastore['beer_lahvove'],
               text=df_datastore['beer_lahvove']),
        go.Bar(name='Cepovane', x=df_datastore['precautions'], y=df_datastore['beer_cepovane'],
               text=df_datastore['beer_cepovane']),
        go.Scatter(name='Infikovani (x10 zoom)', x=df_datastore['precautions'], y=df_datastore['epi_infected']*10,
                   text=df_datastore['epi_infected'], hovertext=df_datastore['epi_infected'])
    ])
    fig.update_layout(barmode='stack', template='plotly_dark',
                      legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="right", x=1))
    #fig.show()
    path = os.path.join(os.path.join(os.getcwd(), 'data/results/{}_final_results.html'.format(max_steps)))
    fig.write_html(path)

def run(params_library, iteration=''):
    """

    :param params_library:
    :return:
    """
    df_datastore = pd.DataFrame()
    max_steps = params_library[0]['fixed_params']['max_steps']
    print('\nSteps to be simulated =', max_steps, f'({max_steps/24} days) for each simulation scenario',
          '(multiprocessing mode)')

    if iteration:
        if params_library[0]['fixed_params']['seed']:
            # TODO: implementace iteraci
            pass

    for storybook in params_library:
        batch_run = BatchRunnerMP(BeerModel, nr_processes=os.cpu_count()-1,
                                  variable_parameters=storybook['variable_params'],
                                  fixed_parameters=storybook['fixed_params'],
                                  iterations=1,
                                  max_steps=max_steps,
                                  model_reporters={
                                      "beer": get_beer_results, "epi": get_epidemic_results, "time": get_sim_duration
                                  })
        batch_run.run_all()
        run_data = batch_run.get_model_vars_dataframe()
        df_datastore = df_datastore.append(run_data, sort=False, ignore_index=True)

    to_drop = ['Run']
    for i, col in enumerate(df_datastore.columns.values):
        if not df_datastore.empty and type(df_datastore.iat[0, i]) == dict:
            df_datastore = df_datastore.join(df_datastore[col].apply(pd.Series))
            df_datastore.rename(columns=dict(zip(df_datastore[col].values[0].keys(),
                                                 [f'{col}_{k}' for k in df_datastore[col].values[0].keys()])),
                                inplace=True)
            to_drop.append(col)
    df_datastore.drop(columns=to_drop, axis=1, inplace=True)
    if 'precautions' in df_datastore.columns.values:
        df_datastore.loc[(df_datastore['precautions'].isna()), 'precautions'] = df_datastore['simtype']
    else:
        df_datastore['precautions'] = df_datastore['simtype']

    df_datastore['scenario_rating'] = df_datastore['beer_cepovane'] + df_datastore['beer_lahvove'] - \
                                      10*df_datastore['epi_infected'] - 1000*df_datastore['epi_death_agents']

    if iteration:
        iteration = f'_{iteration}'
    path = os.path.join(os.path.join(os.getcwd(), 'data/results/{}_final_results{}.csv'.format(max_steps, iteration)))
    df_datastore.to_csv(path, sep=';')
    final_vizualizer(df_datastore, max_steps)
