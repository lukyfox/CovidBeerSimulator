import numpy as np
import pandas as pd
import random
import time
import os
import json


def run(seed=42):
    """

    :param seed:
    :return:
    """
    random.seed(seed)
    data_path = os.path.join(os.getcwd(), 'data') # cesta ke slozce zdroju a vystupu
    with open(os.path.join(data_path, 'source\config_gen.json')) as file:
        data = json.loads(file.read())

    #df_age = pd.read_csv(r'D:\FIM\_StZZ\data\DP\populace.csv', sep=';')
    df_age = pd.DataFrame.from_dict(data['populace'])
    assert sum(df_age['podil_muzu'])+sum(df_age['podil_zen']) == 1.0, 'Pomerne rozlozeni populace v csv neni rovno 1 - zpracovani preruseno'
    soc_size = 1100 # vysledny pocet agentu se muze lisit v radech jednotek z duvodu zaokrouhleni

    df_age['pocet_muzu'] = (soc_size * df_age['podil_muzu']).round(0).astype(int)
    df_age['pocet_zen'] = (soc_size * df_age['podil_zen']).round(0).astype(int)
    df_age.reset_index(inplace=True, drop=True)

    print('Generuji zakladni kameny spolecnosti')
    df_agents = pd.DataFrame()
    for r in df_age.itertuples():
        print(f"Vygenerovana vekova kategorie {r.kategorie}")
        for item in range(r.pocet_muzu):
            df_agents = df_agents.append(pd.Series(data={
                'age': random.randint(int(r.kategorie.split('-')[0]),int(r.kategorie.split('-')[1])),
                'age_categ': r.kategorie,
                'sex': 'M',
                'sickness_count': 0,
                'sicktype': np.nan,
                'inkubation_period': np.nan,
                'sickness_period': np.nan,
                'sickness_result': np.nan,
                'infected_in_step': np.nan,
                'immunity_duration': np.nan,
                'house_id': np.nan,
                'work_id': np.nan,
                'work_type': np.nan
            }), ignore_index = True)
        for item in range(r.pocet_zen):
            df_agents = df_agents.append(pd.Series(data={
                'age': random.randint(int(r.kategorie.split('-')[0]),int(r.kategorie.split('-')[1])),
                'age_categ': r.kategorie,
                'sex': 'Z',
                'sickness_count': 0,
                'sicktype': np.nan,
                'inkubation_period': np.nan,
                'sickness_period': np.nan,
                'sickness_result': np.nan,
                'infected_in_step': np.nan,
                'immunity_duration': np.nan,
                'house_id': np.nan,
                'work_id': np.nan,
                'work_type': np.nan
            }), ignore_index = True)
    print(f'Vygenerovano {df_agents.shape[0]} agentu')

    df_agents.reset_index(inplace=True, drop=True)


    # generovani spolecnych domacnosti
    print('Generuji spolecne domacnosti agentu')

    df_household = pd.DataFrame.from_dict(data['domacnosti'])
    df_household['pocet_clenu_domacnosti'] = df_household.index.astype(int)
    assert sum(df_household['podil_domacnosti_dle_velikosti']) == 1.0, 'Pomerne rozlozeni populace v klici domacnosti neni rovno 1 - zpracovani preruseno'

    df_household['pocet_domacnosti'] = (df_agents.shape[0] / df_household['pocet_clenu_domacnosti'] * df_household['podil_domacnosti_dle_velikosti']).round(0).astype(int)
    df_household['pocet_lidi_v_kategorii'] = df_household['pocet_clenu_domacnosti'] * df_household['pocet_domacnosti']

    households = {}
    i = 0
    for r in df_household.iloc[::-1].itertuples():
        for house_id in range(1, r.pocet_domacnosti+1):
            house_id += i
            households[house_id] = r.pocet_clenu_domacnosti
            members_count_to_assign = 0
            free_capacity = r.pocet_clenu_domacnosti - df_agents.loc[(df_agents['house_id']==house_id)].shape[0]
            while free_capacity > 0:
                if r.pocet_clenu_domacnosti > 1:
                    mask_free_kids = (df_agents['age'] < 20) & (df_agents['house_id'].isna())
                    if any(mask_free_kids):
                        members_count_to_assign = random.randint(
                            1, min([r.pocet_clenu_domacnosti-2 if r.pocet_clenu_domacnosti > 2 else 1, df_agents.loc[mask_free_kids].shape[0], free_capacity]))
                        df_random_kids_selection = df_agents[mask_free_kids].sample(members_count_to_assign)
                        df_agents.loc[df_random_kids_selection.index, 'house_id'] = house_id
                    free_capacity = r.pocet_clenu_domacnosti - df_agents.loc[(df_agents['house_id']==house_id)].shape[0]
                if free_capacity > 0 and r.pocet_clenu_domacnosti > 1:
                    # pokud je volna kapacita, prirazuji rodice - dospeli agenti prirazeni k detem musi mit
                    # odpovidajici vek (aby 10-ti lete dite nesdilelo domacnost s 20-ti nebo 80-ti letym rodicem),
                    # coby fluidne pokrokovy developer pohlavi naopak neresim
                    mask_free_parents = (df_agents['age'].between(
                        df_random_kids_selection['age'].max() + 19, df_random_kids_selection['age'].min() + 45)) & \
                                        (df_agents['house_id'].isna())
                    if any(mask_free_parents):
                        members_count_to_assign = random.randint(
                            1, min(r.pocet_clenu_domacnosti-members_count_to_assign, df_agents.loc[mask_free_parents].shape[0], free_capacity))
                        df_agents.loc[df_agents[mask_free_parents].sample(members_count_to_assign).index, 'house_id'] = house_id
                        free_capacity = r.pocet_clenu_domacnosti - df_agents.loc[(df_agents['house_id']==house_id)].shape[0]
                if free_capacity > 0 and r.pocet_clenu_domacnosti > 1:
                    # pokud je stale volna kapacita, prirazuji prarodice
                    mask_free_grandparents = (df_agents['age'].between(
                        df_random_kids_selection['age'].max() + 49, df_random_kids_selection['age'].min() + 75)) & \
                                        (df_agents['house_id'].isna())
                    if any(mask_free_grandparents):
                        members_count_to_assign = random.randint(
                            1, min(2, df_agents.loc[mask_free_grandparents].shape[0], free_capacity))
                        df_agents.loc[df_agents[mask_free_grandparents].sample(members_count_to_assign).index, 'house_id'] = house_id
                        free_capacity = r.pocet_clenu_domacnosti - df_agents.loc[(df_agents['house_id']==house_id)].shape[0]
                if free_capacity > 0:
                    # a na konec jsou na rade jacikoliv jini dospeli (prarodice, pribuzni,...)
                    mask_free_adults = (df_agents['age'] > 19) & (df_agents['house_id'].isna())
                    if any(mask_free_adults):
                        if r.pocet_clenu_domacnosti == 1:
                            df_agents.loc[df_agents[mask_free_adults].sample(1).index, 'house_id'] = house_id
                        else:
                            members_count_to_assign = random.randint(
                                1, min(r.pocet_clenu_domacnosti-members_count_to_assign, df_agents.loc[mask_free_adults].shape[0], free_capacity))
                            df_agents.loc[df_agents[mask_free_adults].sample(members_count_to_assign).index, 'house_id'] = house_id
                # nakonec opet prepocitam, kolik volneho mista jeste v domacnosti zbyva a pripadne zacinam novy pruchod
                free_capacity = r.pocet_clenu_domacnosti - df_agents.loc[(df_agents['house_id']==house_id)].shape[0]
                if df_agents.loc[(df_agents['house_id'].isna())].shape[0] == 0:
                    # pokud uz nejsou volni agenti, nastavim free_capacity rucne na 0 (jinak nekonecny cyklus)
                    free_capacity = 0
        # prenastavim citac pro nove cislo domacnosti
        i = house_id

    # pokud by i po generovani domacnosti zbyvali volni agenti (bez prirazenych domacnosti), priradim je do jednoclenne
    # domacnosti (nova ciselna rada pres range)
    not_assigned = (df_agents['house_id'].isna())
    start = int(df_agents['house_id'].max()+1)
    stop = int(start+df_agents.loc[not_assigned].shape[0])
    df_agents.loc[not_assigned, 'house_id'] = range(start, stop)
    if stop-start > 1:
        print(f"Pozor, domacnosti {start}..{stop} byly generovany dodatecne (kontrola kodu?)")

    # generovani skolni dochazky a rodicovske
    print('Generuji pracovni, skolni a domaci uvazky agentu')
    #df_podniky = pd.read_csv(r'D:\FIM\_StZZ\data\DP\podniky.csv', sep=';', nrows=1)
    df_podniky = pd.DataFrame.from_dict(data['podniky'])
    #pocet_skol = int(df_agents[df_agents['age']<20].shape[0]) // 300
    #pocet_skol = 1 if pocet_skol < 1 else int(pocet_skol)
    pocet_skol = np.ceil(df_agents[df_agents['age']<=19].shape[0]/df_podniky['pocet_zaku_na_skole'])
    df_skola = pd.DataFrame({'skola_id': range(int(df_agents['house_id'].max()+1), int(df_agents['house_id'].max()+1+pocet_skol))})
    for r in df_agents[df_agents['age']<20].itertuples():
        if r.age < 5:
            # deti mladsi 5-ti let zustavaji doma s jednim rodicem (work_id = 0)
            df_agents.loc[r.Index, 'work_id'] = r.house_id
            mask_parent = (df_agents['house_id']==r.house_id) & (df_agents['age']>19)
            if df_agents.loc[(df_agents['house_id']==r.house_id) & (df_agents['age']>19)].shape[0]>0:
                df_agents.loc[df_agents[mask_parent].sample(random_state=seed).index, 'work_id'] = r.house_id
        else:
            # deti od 5 let chodi do skoly/skolky
            df_agents.loc[r.Index, 'work_id'] = df_skola.sample(random_state=seed)['skola_id'].item()
            df_agents.loc[r.Index, 'work_type'] = 'skola'
    df_agents.loc[df_agents[(df_agents['work_id']==df_agents['house_id'])].index, 'work_type'] = 'doma'

    # generovani pracovnich uvazku
    df_firma = pd.DataFrame.from_dict(data['firmy'])
    mask_pracujici_prodvek = (df_agents['age'].between(20, 64)) & (df_agents['work_id'].isna())
    df_agents.loc[df_agents[mask_pracujici_prodvek].index, 'work_id'] = -1
    pocet_zamcu = df_agents[df_agents['work_id']==-1].shape[0]
    # prepocet poctu firem
    for firma in df_firma.itertuples():
        celkem_z = pocet_zamcu * firma.podil
        pocet_firem = int(celkem_z * 2.0 / (firma.max_velikost-firma.min_velikost))
        df_firma.loc[firma.Index, 'pocet_firem'] = pocet_firem
    df_firma['pocet_firem'] = df_firma['pocet_firem'].astype(int)
    for firma in df_firma.itertuples():
        max_id = df_agents['work_id'].max()
        for pracoviste in range(1, firma.pocet_firem+1):
            mask_pracovnici = (df_agents['work_id']==-1)
            if df_agents[mask_pracovnici].shape[0] < 1:
                break
            zamestnanci = df_agents[mask_pracovnici].sample(random.randint(firma.min_velikost, firma.max_velikost), random_state=seed, replace=True).index
            df_agents.loc[zamestnanci, 'work_id'] = max_id+pracoviste
            df_agents.loc[zamestnanci, 'work_type'] = 'firma'


    # generovani duchodu
    mask_duchodce = (df_agents['age']>64) & (df_agents['work_id'].isna())
    df_agents.loc[df_agents[mask_duchodce].index, 'work_type'] = 'doma'
    df_agents.loc[df_agents[mask_duchodce].index, 'work_id'] = df_agents['house_id']

    # generovani typu a prubehu onemocneni
    print('Generuji zdravotni matici agentu')
    for age in df_age.itertuples():
        age_group = (int(age.kategorie.split('-')[0]), int(age.kategorie.split('-')[1]))
        # muzi
        mask_prubeh_typ = (df_agents['sex']=='M') & (df_agents['age'].between(age_group[0],age_group[1]))
        #mask_prubeh_typ_asymptom = mask_prubeh_typ & (df_agents['sicktype']=='asymptomatic')
        #mask_prubeh_typ_mild = mask_prubeh_typ & (df_agents['sicktype']=='mild')
        #mask_prubeh_typ_severe = mask_prubeh_typ & (df_agents['sicktype']=='severe')

        mask_prubeh_typ_unassigned = mask_prubeh_typ & (df_agents['sicktype'].isna())
        df_agents.loc[df_agents[mask_prubeh_typ_unassigned].sample(frac=age.tezky_prubeh_hospitalizace_muzi, random_state=seed).index, 'sicktype'] = 'severe'
        mask_prubeh_typ_unassigned = mask_prubeh_typ & (df_agents['sicktype'].isna())
        df_agents.loc[df_agents[mask_prubeh_typ_unassigned].sample(frac=age.asymp_podil_muzi, random_state=seed).index, 'sicktype'] = 'asymptomatic'
        mask_prubeh_typ_unassigned = mask_prubeh_typ & (df_agents['sicktype'].isna())
        df_agents.loc[df_agents[mask_prubeh_typ_unassigned].index, 'sicktype'] = 'mild'

        inkubacni_doba = (int(age.inkubacni_doba.split('-')[0]), int(age.inkubacni_doba.split('-')[1]))
        delka_nemoci_mild = (int(age.symptomaticka_doba_stredni_prubeh.split('-')[0]), int(age.symptomaticka_doba_stredni_prubeh.split('-')[1]))
        delka_nemoci_severe = (int(age.symptomaticka_doba_tezky_prubeh.split('-')[0]), int(age.symptomaticka_doba_tezky_prubeh.split('-')[1]))

        arr = [int(random.randint(inkubacni_doba[0],inkubacni_doba[1])) for i in range(df_agents[mask_prubeh_typ].shape[0])]
        df_agents.loc[df_agents[mask_prubeh_typ].index, 'inkubation_period'] = arr

        mask_prubeh_typ_asymptom = mask_prubeh_typ & (df_agents['sicktype']=='asymptomatic')
        arr = [int(random.randint(delka_nemoci_mild[0],delka_nemoci_mild[1])) for i in range(df_agents[mask_prubeh_typ_asymptom].shape[0])]
        df_agents.loc[df_agents[mask_prubeh_typ_asymptom].index, 'sickness_period'] = arr

        mask_prubeh_typ_mild = mask_prubeh_typ & (df_agents['sicktype']=='mild')
        arr = [int(random.randint(delka_nemoci_mild[0],delka_nemoci_mild[1])) for i in range(df_agents[mask_prubeh_typ_mild].shape[0])]
        df_agents.loc[df_agents[mask_prubeh_typ_mild].index, 'sickness_period'] = arr

        mask_prubeh_typ_severe = mask_prubeh_typ & (df_agents['sicktype']=='severe')
        arr = [int(random.randint(delka_nemoci_severe[0],delka_nemoci_severe[1])) for i in range(df_agents[mask_prubeh_typ_severe].shape[0])]
        df_agents.loc[df_agents[mask_prubeh_typ_severe].index, 'sickness_period'] = arr
        df_agents.loc[df_agents[mask_prubeh_typ_severe].sample(frac=age.umrti_pri_hospitalizaci_muzi, random_state=seed).index, 'sickness_result'] = 'exitus'

        # zeny
        mask_prubeh_typ = (df_agents['sex']=='Z') & (df_agents['age'].between(age_group[0],age_group[1]))
        # mask_prubeh_typ_unassigned = mask_prubeh_typ & (df_agents['sicktype'].isna())
        # mask_prubeh_typ_asymptom = mask_prubeh_typ & (df_agents['sicktype']=='asymptomatic')
        # mask_prubeh_typ_mild = mask_prubeh_typ & (df_agents['sicktype']=='mild')
        # mask_prubeh_typ_severe = mask_prubeh_typ & (df_agents['sicktype']=='severe')
        mask_prubeh_typ_unassigned = mask_prubeh_typ & (df_agents['sicktype'].isna())
        df_agents.loc[df_agents[mask_prubeh_typ_unassigned].sample(frac=age.tezky_prubeh_hospitalizace_zeny, random_state=seed).index, 'sicktype'] = 'severe'
        mask_prubeh_typ_unassigned = mask_prubeh_typ & (df_agents['sicktype'].isna())
        df_agents.loc[df_agents[mask_prubeh_typ_unassigned].sample(frac=age.asymp_podil_zeny, random_state=seed).index, 'sicktype'] = 'asymptomatic'
        mask_prubeh_typ_unassigned = mask_prubeh_typ & (df_agents['sicktype'].isna())
        df_agents.loc[df_agents[mask_prubeh_typ_unassigned].index, 'sicktype'] = 'mild'

        arr = [int(random.randint(inkubacni_doba[0],inkubacni_doba[1])) for i in range(df_agents[mask_prubeh_typ].shape[0])]
        df_agents.loc[df_agents[mask_prubeh_typ].index, 'inkubation_period'] = arr

        mask_prubeh_typ_asymptom = mask_prubeh_typ & (df_agents['sicktype']=='asymptomatic')
        arr = [int(random.randint(delka_nemoci_mild[0],delka_nemoci_mild[1])) for i in range(df_agents[mask_prubeh_typ_asymptom].shape[0])]
        df_agents.loc[df_agents[mask_prubeh_typ_asymptom].index, 'sickness_period'] = arr

        mask_prubeh_typ_mild = mask_prubeh_typ & (df_agents['sicktype']=='mild')
        arr = [int(random.randint(delka_nemoci_mild[0],delka_nemoci_mild[1])) for i in range(df_agents[mask_prubeh_typ_mild].shape[0])]
        df_agents.loc[df_agents[mask_prubeh_typ_mild].index, 'sickness_period'] = arr

        mask_prubeh_typ_severe = mask_prubeh_typ & (df_agents['sicktype']=='severe')
        arr = [int(random.randint(delka_nemoci_severe[0],delka_nemoci_severe[1])) for i in range(df_agents[mask_prubeh_typ_severe].shape[0])]
        df_agents.loc[df_agents[mask_prubeh_typ_severe].index, 'sickness_period'] = arr
        df_agents.loc[df_agents[mask_prubeh_typ_severe].sample(frac=age.umrti_pri_hospitalizaci_zeny, random_state=seed).index, 'sickness_result'] = 'exitus'

        # generovani infekcni periody - kdy je agent infekcni pro okoli
        df_agents.loc[(df_agents['age'].between(age_group[0], age_group[1])), 'spreader_period_from'] = random.randint(int(age.infekcni_doba_pred_priznaky.split('-')[0]), int(age.infekcni_doba_pred_priznaky.split('-')[1]))

    df_agents.loc[df_agents['spreader_period_from'] > df_agents['inkubation_period'], 'spreader_period_from'] = df_agents['inkubation_period']

    # generovani imunity
    print('Generuji imunitni ochranu agentu')
    #df_imunita = pd.read_csv(r'D:\FIM\_StZZ\data\DP\imunita.csv', sep=';')
    df_imunita = pd.DataFrame.from_dict(data['imunita'])
    for imunita in df_imunita.itertuples():
        imu_doba = (int(imunita.delka_imunity_dny.split('-')[0]),int(imunita.delka_imunity_dny.split('-')[1]))
        mask_imunita_unassigned = (df_agents['immunity_duration'].isna())
        #a = df_agents.loc[mask_imunita_unassigned].shape[0]
        cnt = df_agents.sample(frac=imunita.podil, random_state=seed).shape[0]
        arr = [int(random.randint(imu_doba[0],imu_doba[1])) for i in range(cnt)]
        df_agents.loc[df_agents[mask_imunita_unassigned].sample(cnt, random_state=seed).index, 'immunity_duration'] = arr
    # pokud zustane nekolik zaznamu bez hodnoty (zaokrouhovaci chyba), nastavim 180-denni imunitu
    mask_imunita_unassigned = (df_agents['immunity_duration'].isna())
    if df_agents[mask_imunita_unassigned].shape[0] > 0:
        df_agents.loc[df_agents[mask_imunita_unassigned].index, 'immunity_duration'] = 180

    print('Generuji pivni spotrebu agentu')
    #df_beercon = pd.read_csv(r'D:\FIM\_StZZ\data\DP\pivni_spotreba.csv', sep=';', index_col='kategorie')
    df_beercon = pd.DataFrame.from_dict(data['pivo']).set_index('kategorie', drop=True)
    df_agents['aktualni_tyden'] = 0
    df_agents['tydenni_spotreba_cepovane'] = 0
    df_agents['tydenni_spotreba_lahvove'] = 0
    df_agents['prechod_na_lahvove_podil'] = 0
    for beer_categ in df_beercon.itertuples():
        # generovani spotreby muzu
        mask_beercon_by_age = (df_agents['age'].between(int(beer_categ.Index.split('-')[0]), int(beer_categ.Index.split('-')[1]))) & (df_agents['sex'] == 'M')
        df_agents.loc[df_agents[mask_beercon_by_age].sample(frac=beer_categ.podil_muzi, random_state=seed).index, 'tydenni_spotreba_cepovane'] = beer_categ.konzumace_05_muzi * beer_categ.podil_cepovane
        # podil pivaru pro lahvove nelze vybrat nahodne - jde o jiz definovane konzumenty piva (nelze znovu pouzit frac)
        df_agents.loc[mask_beercon_by_age & (df_agents['tydenni_spotreba_cepovane']>0), 'tydenni_spotreba_lahvove'] = beer_categ.konzumace_05_muzi * (1-beer_categ.podil_cepovane)
        # nahradni pijaci piva - v pripade karanteny, uzavreni restauraci apod. maji agenti urcitou pravdepodobnost nahrazeni piva cepovaneho pivem lahvovym
        # (muze se lisit podle vekovych skupin a agenti musi byt i konzumenty lahvoveho piva)
        df_agents.loc[mask_beercon_by_age & (df_agents['tydenni_spotreba_lahvove']>0), 'prechod_na_lahvove_podil'] = beer_categ.prechod_na_lahvove_podil
        # generovani spotreby zen
        mask_beercon_by_age = (df_agents['age'].between(int(beer_categ.Index.split('-')[0]), int(beer_categ.Index.split('-')[1]))) & (df_agents['sex'] == 'Z')
        df_agents.loc[df_agents[mask_beercon_by_age].sample(frac=beer_categ.podil_zeny, random_state=seed).index, 'tydenni_spotreba_cepovane'] = beer_categ.konzumace_05_zeny * beer_categ.podil_cepovane
        df_agents.loc[mask_beercon_by_age & (df_agents['tydenni_spotreba_cepovane']>0), 'tydenni_spotreba_lahvove'] = beer_categ.konzumace_05_zeny * (1-beer_categ.podil_cepovane)
        df_agents.loc[mask_beercon_by_age & (df_agents['tydenni_spotreba_lahvove']>0), 'prechod_na_lahvove_podil'] = beer_categ.prechod_na_lahvove_podil

    # generovani sveta agentu
    print('Generuji svet agentu')
    #world_size = len(df_agents['work_id'].unique())
    households = sorted(list(df_agents['house_id'].unique()))
    print('\nhouseholds:', households)
    workplaces = sorted(list(df_agents[df_agents['work_type']=='firma']['work_id'].unique()))
    print('\nworkplaces:', workplaces)
    schools = list(df_agents[df_agents['work_type']=='skola']['work_id'].unique())
    print('\nschools:', schools)

    occupied_space = households + workplaces + schools
    world_size = len(occupied_space)

    # urcity pomer firem predstavuje obchody - agenti zde pracuji a chodi i nakupovat
    shops = random.sample(workplaces, int(len(workplaces)*df_podniky['pomer_obchodu_k_firmam']))
    # agenti pracujici v obchodech musi mit worktype = obchod
    df_agents.loc[(df_agents['work_id'].isin(shops)), 'work_type'] = 'obchod'
    # pocet restauraci je pomerove cislo ze vsech firem
    cnt_pub = int(np.ceil(df_agents.shape[0]/df_podniky['pocet_restauraci_na_obyvatele']))
    # vyber agentu pracujicich v malych firmach - nektere z nich se stanou restauracemi (pro simulaci jsou R firmy do 15 zamcu)
    df_agents_in_small_business = df_agents[df_agents['work_type']=='firma']
    pubs = df_agents_in_small_business.groupby('work_id').size().loc[lambda x: x<15].index.to_list()
    # nahodny vyber restauraci s osetrenim (nepravdepodobne) chyby nahodneho vyberu prilis mnoha prvku z maleho rozsahu
    pubs = random.sample(pubs, cnt_pub) if len(pubs) > cnt_pub else pubs
    # agenti pracujici v restauracich musi mit worktype = restaurace
    df_agents.loc[(df_agents['work_id'].isin(pubs)), 'work_type'] = 'restaurace'


    #world_size = len(occupied_space) #+ cnt_pub
    cnt_nature = int(0.1 * world_size)
    # +1 je nemocnice (H)
    world_size += cnt_nature + 1
    # rozmer jedne dimenze matice
    dim = int(np.ceil(np.sqrt(world_size)))
    df_world = pd.DataFrame([range(i*dim, dim+i*dim) for i in range(dim)], index=np.arange(dim), columns=range(dim))
    df_world.sort_index(ascending=False, inplace=True)
    hospital_placed = False
    for line in df_world.itertuples():
        # ke kazdemu agentu ulozim koordinaty (x,y) domova (D) a prace (W/S/R/N)
        for idx, colidx in enumerate(line[1:]):
            # [1:] protoze prvni v sekvenci je index a ten musim preskocit, idx je pak cislo sloupce a line.Index cislo radku
            if colidx in households: #df_agents['house_id'].tolist():
                aa = type(idx)
                #print('house:', colidx, 'in', idx, ',', line.Index, 'for', df_agents.loc[df_agents['house_id']==colidx].shape[0])
                df_agents.loc[df_agents['house_id']==colidx, 'coord_house_xgrid'] = idx
                df_agents.loc[df_agents['house_id']==colidx, 'coord_house_ygrid'] = line.Index
                df_agents.loc[df_agents['house_id']==df_agents['work_id'], 'coord_work_xgrid'] = idx
                df_agents.loc[df_agents['house_id']==df_agents['work_id'], 'coord_work_ygrid'] = line.Index
                df_world.loc[line.Index, idx] = "{" + f"'D':({colidx}, ({idx}, {line.Index}))" + "}"
            if colidx in workplaces: #df_agents['work_id'].tolist():
                aa = type(idx)
                df_agents.loc[df_agents['work_id']==colidx, 'coord_work_xgrid'] = idx
                df_agents.loc[df_agents['work_id']==colidx, 'coord_work_ygrid'] = line.Index
                df_world.loc[line.Index, idx] = "{" + f"'W':({colidx}, ({idx}, {line.Index}))" + "}"
                if colidx in shops:
                    # workplaces mohou byt soucasne i obchodni domy
                    df_world.loc[line.Index, idx] = "{" + f"'WN':({colidx}, ({idx}, {line.Index}))" + "}"
                elif colidx in pubs:
                    # workplaces mohou byt soucasne i restaurace
                    df_world.loc[line.Index, idx] = "{" + f"'WR':({colidx}, ({idx}, {line.Index}))" + "}"
            if colidx in schools:
                df_agents.loc[df_agents['work_id']==colidx, 'coord_work_xgrid'] = idx
                df_agents.loc[df_agents['work_id']==colidx, 'coord_work_ygrid'] = line.Index
                df_world.loc[line.Index, idx] = "{" + f"'S':({colidx}, ({idx}, {line.Index}))" + "}"
            if colidx not in workplaces and colidx not in households and colidx not in schools:
                if not hospital_placed:
                    df_world.loc[line.Index, idx] = "{" + f"'H':({colidx}, ({idx}, {line.Index}))" + "}"
                    hospital_placed = True
                else:
                    df_world.loc[line.Index, idx] = "{" + f"'P':({colidx}, ({idx}, {line.Index}))" + "}"

            #if colidx in households:
            #    df_world.loc[line.Index, idx] = "{" + f"'D':({colidx}, ({idx}, {line.Index}))" + "}"
            #elif colidx in workplaces:
            #    df_world.loc[line.Index, idx] = "{" + f"'W':({colidx}, ({idx}, {line.Index}))" + "}"
            #    if colidx in shops:
            #        # workplaces mohou byt soucasne i obchodni domy
            #        df_world.loc[line.Index, idx] = "{" + f"'WN':({colidx}, ({idx}, {line.Index}))" + "}"
            #    elif colidx in pubs:
            #        # workplaces mohou byt soucasne i restaurace
            #        df_world.loc[line.Index, idx] = "{" + f"'WR':({colidx}, ({idx}, {line.Index}))" + "}"

    # generovani pohybu po domacnostech
    tmp = []
    print('Generuji tydenni pohybovou matici agentu (to bude chvilku trvat)')
    cols = [str(i) for i in range(168)]
    cols.extend(['agent_id'])
    df_agent_moves = pd.DataFrame(columns=cols, data=None)
    df_mobility = pd.read_csv(r'D:\FIM\_StZZ\data\DP\mobilita.csv', sep=';')
    houses = list(df_agents['house_id'].unique())
    start = time.time()
    for processed, house_id in enumerate(houses):
        agents_in_house = df_agents[df_agents['house_id']==house_id].sort_values(by=['age'])
        for agent in agents_in_house.itertuples():
            arr = []
            mask_mobility_by_age = (df_mobility['kategorie']==agent.age_categ)
            while len(arr) < 168:
                for idx, col in enumerate(df_mobility.columns):
                    if col not in ('oblast', 'kategorie'):
                        fixed_walk = df_mobility[mask_mobility_by_age & (df_mobility[col]==1)].index
                        if fixed_walk.size == 0:
                            random_walk = random.random()
                            for prob in df_mobility[mask_mobility_by_age].itertuples():
                                random_walk -= prob[idx+1]
                                if random_walk <= 0:
                                    arr.append(df_mobility.loc[prob.Index, 'oblast'])
                                    break
                        else:
                            arr.append(df_mobility.loc[fixed_walk.values[0], 'oblast'])
            # agenti s nenulovou spotrebou cepovaneho piva musi mit v moves alespon 1 navstevu restaurace (nahodne 1-7)
            if agent.tydenni_spotreba_cepovane != 0 and 'R' not in arr:
                tmp.append(agent.Index)
                for _ in range(random.randint(1, 7)):
                    # navsteva v nahodny den
                    day_of_visit = random.randint(0, 6)
                    # nahodna navsteva mezi 16:00 a pulnoci
                    arr[day_of_visit*24 + random.randint(16, 23)] = 'R'

            arr = dict(zip(df_agent_moves.columns, arr))
            arr['agent_id'] = agent.Index
            df_agent_moves = df_agent_moves.append(arr, ignore_index=True)

        if (processed+1) % 100 == 0:
            print('Zpracovan pohyb clenu', processed+1, 'domacnosti z', len(houses))
        if processed == 0:
            start = time.time() - start
            print('...ale urcite mene nez',(start * len(houses))//60 + 1,'minut')
    df_agent_moves.set_index(['agent_id'], inplace=True, drop=True)
    df_agent_moves.sort_index(inplace=True)
    # print('df_agents po zpracovani pohybu =', df_agents.shape[0])

    # deti do 5 let v simualci nechodi do skolky a nektery z dospelych je s nimi doma => kopiruje jejich pohybovou matici
    print('Nastavuji (pra)rodicovske dovolene')
    for house_id in houses:
        agents_in_house = df_agents[df_agents['house_id']==house_id]
        if any(agents_in_house['age']<5):
            if all(agents_in_house['age']<5):
                # Note: chyba se sirotky byla sice opravena, ale tak pro jistotu...
                print('Pozor, sirotek v dome c.', house_id, f'({agents_in_house["age"].to_list()})')
            else:
                mask_maternity_leave = (agents_in_house['age']>19) & (agents_in_house['age']<75)
                mask_kids = (agents_in_house['age']<5)
                restore = []
                if agents_in_house.loc[mask_maternity_leave & (agents_in_house['tydenni_spotreba_cepovane']==0)].shape[0] > 0:
                    # pokud se mezi vhodnymi agenty v domacnosti vyskytuje restauracni abstinent, pak je to
                    # preferovany (pra)rodic pro (pra)rodicovskou
                    nanny = agents_in_house.loc[mask_maternity_leave & (agents_in_house['tydenni_spotreba_cepovane']==0)].sample(random_state=seed).index[0]
                else:
                    # pokud vsichni dospeli v domacnosti piji pivo v restauraci, pak se toho urcite nevzdaji - musim
                    # tedy vytahnout z matice mobility rodice indexy lokaci R. Pokud restore obsahuje uschovane
                    # navstevy R, nakopiruji je pozdeji zpet do mobility (pra)rodice (mamka je na pivku, prcek v kocarku),
                    # jedna se tedy o neco jako merge mobilit prcka (master) a mamky (slave, az na R)
                    nanny = agents_in_house.loc[mask_maternity_leave].sample(random_state=seed).index[0]
                    restore = [i for i, loc in enumerate(df_agent_moves.loc[nanny].to_list()) if loc == "R"]

                # vyberu vsechny male deti v domacnosti a jedno zvolim za template kida
                df_kids = df_agent_moves.loc[agents_in_house.loc[mask_kids].index]
                kid = random.sample(df_kids.index.to_list(), 1)[0]
                # prenesu pohybovy retezec ditete na rodice
                df_agent_moves.iloc[(df_agent_moves.index.isin([nanny]))] = df_agent_moves.loc[[kid]]
                # a ulozene R lokace zpatky na rodice
                df_agent_moves.iloc[(df_agent_moves.index.isin([nanny]))] = df_agent_moves.loc[[nanny]].apply(lambda loc: 'R' if df_agent_moves.columns.get_loc(loc.name) in restore else loc)
    # print('df_agents po zpracovani materskych =', df_agents.shape[0])

    print('Ukladam grid pro pouziti v simulaci')
    df_world.to_csv(os.path.join(data_path, 'source\df_grid.csv'), sep=';')

    print('Ukladam pohybovou matici pro pouziti v simulaci')
    df_agent_moves.to_csv(os.path.join(data_path, 'source\df_agent_moves.csv'), sep=';')

    print('Ukladam agenty pro pouziti v simulaci')
    df_agents.to_csv(os.path.join(data_path, 'source\df_agents.csv'), sep=';')

    print('Socialni generator uspesne dokoncil cinnost -> cas na pivo...nebo na spusteni simulace')
