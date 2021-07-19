# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import pandas as pd
import os

from library import BeerModel, BeerAgent, Model # MyDataCollector,
import matplotlib.pyplot as plot
from mesa.visualization.modules import ChartModule
from mesa.visualization.ModularVisualization import ModularServer
from mesa.batchrunner import BatchRunner, BatchRunnerMP
import plotly.graph_objects as go

max_steps = 8760 # 365-ti denni simulace
max_steps = 24 #2160 #720 # 30-ti denni simulace

def get_beer_results(model):
    # pri multiprocessingu musim uvest identifikaci scenare, vypis neni hned pod informaci o startu scenare
    print("*"*25,'\n',f'Scenario resuts for {model.simtype}: {",".join([p["name"]+"(tt:"+str(p["trigger_threshold"])+")" for p in model.applied_precautions])}', sep='')
    print(f"Beer consumed: {round(model.df_results.tail(1)['beer_consumption_sum_cepovane'].values[0],2)} l",
          f"cepovane, {round(model.df_results.tail(1)['beer_consumption_sum_lahvove'].values[0],2)} l lahvove")
    return {
        'cepovane': round(model.df_results.tail(1)['beer_consumption_sum_cepovane'].values[0], 2),
        'lahvove': round(model.df_results.tail(1)['beer_consumption_sum_lahvove'].values[0], 2)
    }

def get_epidemic_results(model):
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

def get_results(model):
    return model.df_results

df_datastore = pd.DataFrame()

if __name__ == '__main__':
    #for max_steps in [2160, 4320]:
    for max_steps in [24]:
        print('\nSteps to be simulated =', max_steps, f'({max_steps/24} days) for each simulation scenario',
              '(multiprocessing mode)')

        #beer_model = BeerModel(simtype='covid', max_steps=max_steps, precautions='mask_r!1,test_w!0')
        #for i in range(max_steps):
        #    beer_model.step()

        # spusteni BatchRunneru pro pripad bez opatreni
        # simtype = 'no covid' pro referencni hodnoty (spotreba piva za normalnich okolnosti)
        # simtype = 'covid' pro modelovani epidemie bez opatreni (spotreba piva za epidemie)
        precautions = ['yes', 'no']
        precautions = ['yes']

        if 'no' in precautions:
            variable_params = {'simtype': ['no covid', 'covid']}
            fixed_params = {'max_steps': max_steps}
            batch_run = BatchRunnerMP(BeerModel, nr_processes=2,
                                     variable_parameters=variable_params,
                                     fixed_parameters=fixed_params,
                                     iterations=1,
                                     max_steps=max_steps,
                                     model_reporters={"beercon": get_beer_results, "epi": get_epidemic_results}
                                     )
            batch_run.run_all()
            run_data = batch_run.get_model_vars_dataframe()
            df_datastore = df_datastore.append(run_data, sort=False, ignore_index=True)


        if 'yes' in precautions:
            # spusteni BatchRunneru za epidemie a s opatrenimi - opatreni mohou byt kombinovana, maji ruzne mody dane retezcem
            # za podtrzitkem (u nekterych opatreni se mohou mody skladat, u jinych se vylucuji a lze pouzit jen jeden):
            # - ochrana dychacich cest (mask): mask, mask_r = zaklad s vychozimi hodnotami modelu, ucinnost rousek je
            #   snizena v urcitych oblastech; mask_i = idealni stav, kdy maji rousky vzdy a vsude plnou ucinnost;
            #   mody se vylucuji
            # - karantena (quarantine): zakladni karanteni opatreni je karantena na infikovane: nastup symptomu mild/severe
            #   nebo pozitivni test. To je aplikovano vzdy a bez ohledu na jakakoliv opatreni. Opatreni quarantine
            #   a quarantine_d = rozsireni skupiny o karantenu na cleny stejne domacnosti; quarantine_w = na cleny stejne firmy
            #   nebo skoly; mody lze skladat (_wd)
            # - uplne omezeni mobility (lockdown): lockdown = uzavreni vsech lokaci, agenti zustavaji doma
            # - sektorove omezeni (sector): sector, sector_r = uzavreni restauraci, sector_w = uzavreni pracovist a skol; mody
            #   lze skladat (_rw)
            # - testovani (test): test, test_w = testovani probiha na pracovisti; test_d = testovani probiha doma (nebo odberove
            #   misto); mody lze skladat (_wd)
            # - chytra aplikace (app): app, app_m = kontakty symptomaticky nemocneho/pozitivne testovaneho zacnou nosit rousku;
            #   app_q = kontakty jdou do karanteny; app_t = kontakty v nasledujicim kroku podstoupi test; mody se vylucuji
            # Opatreni lze kombinovat v retezci oddelovanem carkou (napr. "mask,quarantine_d,test_dw" spusti scenar
            #   s kombinaci opatreni: rousky + karantena na cleny domacnosti + testovani na pracovistich, skolach a doma)
            # U opatreni lze volit spousteci mez (trigger_threshold, tt) pomoci cisla na konci opatreni oddeleneho
            #   znakem "!", tato hodnota pak prepise vychozi trigger_threshold. Hodnota 0 znamena, ze opatreni je
            #   v platnosti od pocatku, jine hodnoty jsou zavisle na pritomnosti opatreni test v simulaci - pokud je
            #   testovani soucasti simulace, pak cislo oznacuje pocet pozitivne testovanych za poslednich 7 dnu, pokud test
            #   neni soucasti opatreni, pak cislo oznacuje pocet mild/severe symptomatickych nemocnych v poslednich 7 dnech.
            #   Pr.1: "mask!10,quarantine_d!5,test_dw!0" je simulace, kde je opatreni testovani doma a na pracovisti/skole
            #   aplikovano od pocatku, opatreni karanteny na spolecnou domacnost je aktivovano pri vice nez 5-ti pozitivnich
            #   testech kumulativne za poslednich 7 dnu a noseni ochrany dychacich cest je aktivovano pri 10-ti pozitivnich
            #   testech
            #   Pr.2: v simulaci "sector_r!1,lockdown!50,test_d!25" je aktivovano sektorove opatreni v podobe uzavreni
            #   restauraci pri prvnim vyskytu symptomatickeho nemocneho v symptomaticke fazi onemocneni, povinne testovani
            #   doma/na odbernich mistech je aktivovano, pokud pocet novych prechodu do symptomaticke faze za poslednich
            #   7 dnu prekroci 25 a lockdown je aplikovan ve chvili, kdy je v poslednich 7 dnech zachyceno alespon 50
            #   pozitivnich vysledku testu (testovani se aktivuje v prubehu simulace a vsechna prozatim neaktivovana
            #   opatreni s nim pocitaji)
            variable_params = {"precautions": [
                # opatreni ODD - mask_i jsou zde hlavne kvuli porovnani s idealnim (ale neprilis realnym) stavem
                #'mask_i!0', 'mask_i!1', 'mask_r!0', 'mask_r!1', 'mask_r!1,test_dw!0',
                #'quarantine_d!0', 'quarantine_d!1', 'quarantine_dw!0', 'quarantine_dw!1', 'quarantine_d!0,test_dw!0',
                #'lockdown!1', 'sector_r!1', 'sector_rw!1', 'sector_r!1,test_dw!0',
                #'lockdown!1,test_dw!0',
                'app_it!0', 'app_iq!0', 'app_im!0',
                # eRouska od pocatku s nastavenim ODD pro kontakty, globalni ODD uvedeno kvuli parametrum masek
                # (nebo start pri 1000 nemocnych za 7 dnu)
                'app_im!0,mask_r!1000' #,
                # to same jako predchozi, jen s pridanim testovani od 1. nemocneho (zjisteni vyhodnosti testu)
                #'app_im!0,mask_r!1000,test_w!1',
                #'app_tm!0,sector_rw!25'
                ]}
            fixed_params = {'simtype': 'covid', 'max_steps': max_steps}
            batch_run = BatchRunnerMP(BeerModel, nr_processes=os.cpu_count()-1,
                                    variable_parameters=variable_params,
                                    fixed_parameters=fixed_params,
                                    iterations=1,
                                    max_steps=max_steps,
                                    model_reporters={"beercon": get_beer_results, "epi": get_epidemic_results}
                                    )
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
        df_datastore.loc[(df_datastore['precautions'].isna()), 'precautions'] = df_datastore['simtype']
        path = os.path.join(os.path.join(os.getcwd(), 'data/results/{}_final_results.csv'.format(max_steps)))
        df_datastore.to_csv(path, sep=';')
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
        #fig.show()
        path = os.path.join(os.path.join(os.getcwd(), 'data/results/{}_final_results.html'.format(max_steps)))
        fig.write_html(path)
        #BeerModel.nice_vizualizer2(df_datastore)

    print('All the hard work done!')
