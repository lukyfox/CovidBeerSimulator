import ast, math, sys
import os

from mesa import Agent, Model
from mesa.time import RandomActivation
from mesa.space import MultiGrid
# from mesa.datacollection import DataCollector
import pandas as pd
import numpy as np
import itertools, time, random, json
import plotly.graph_objects as go
import plotly.express as px
import plotly.subplots as ps

HOME = 'D'
WORK = 'W'
SCHOOL = 'S'
NATURE = 'P'
PUB = 'R'
SHOP = 'N'

seed = 42
random.seed(seed)

class BeerAgent(Agent):
    """
    BeerAgent class:
    -> trida agentu popijejicich pivo a nebo taky vubec ne (pod 18 jen limcu...kdybych to tak taky delal,
    mohl jsem byt dneska doktor)
    """
    def __init__(self, agent, model, route_plan, random_seed = 42):
        """
        Konstruktor prebira informace o agentech z csv a pouziva jednotny seed pro vsechna random cisla v instanci(ch)
        :param agent: informace o agentovi nactena z csv (vek, pohlavi, spolecna domacnost apod.)
        :param model: model, ke kteremu je agent prirazen
        :param route_plan: pohybovy retezec agenta nacteny y csv
        :param random_seed: seed pro random hodnoty
        """

        super().__init__(agent.Index, model)
        self.random.seed(random_seed) # nastaveni seedu pro generator (pro reproducibilitu experimentu)
        self.age = agent.age # vek agenta
        self.sex = agent.sex # pohlavi agenta
        self.sicktype = agent.sicktype # typ onemocneni po projeveni priznaku (asymptomatic, mild, severe)
        self.house_id = agent.house_id # koordinaty (pos) domovske bunky (TODO: nahrazeni xcoords a ycoords)
        self.work_id = agent.work_id # koordinaty (pos) bunky zamestnani / skoly (TODO: nahrazeni xcoords a ycoords)
        self.age_categ = agent.age_categ # vekova kategorie (pro snizeni vypocetniho casu)
        self.immunity_duration = agent.immunity_duration * 24 # pocet stepu, v nichz je agent imunni (alias imd)
        self.inkubation_period = agent.inkubation_period * 24 # pocet stepu od nakazy po projeveni priznaku (alias ip)
        self.spreader_period_from = agent.spreader_period_from * 24 # pocet stepu s maximalni virulenci pred projevenim priznaku (alias spf)
        self.sickness_period = agent.sickness_period * 24 # pocet stepu onemocneni v priznakove fazi (alias sp)

        self.infected_in_step = 0 # cislo stepu, ve kterem doslo k infikaci, iis = 0 pro zdraveho agenta, tj. Suspicious (alias iis)
        self.infected_by = [] # zdroj infekce (-1 pro "vnejsi" nakazu, nebo unique_id roznasece), kvuli omezene imunite se muze nakazit vicekrat
        self.infected_at_place = [] # misto infekce
        self.non_infectious_till = 0 # cislo kroku, do ktereho je nakazeny agent neinfekcni (iis + ip - sfp)
        self.super_spreader_till = 0 # cislo kroku, do ktereho je agent v inkubacni dobe bezpriznakovym superprenasecem (iis + ip)
        self.regular_illness_till = 0 # cislo kroku, do ktereho je agent nemocny v symptomaticke fazi (iis + ip + sp),
        # hodnota regular_illness_till se linearne snizuje v prubehu casu v rozsahu 100..0 - ir*(sp-n-(iis+ip))/sp
        self.immune_till = 0 # cislo stepu, do ktereho je vyleceny agent imunni (iis + ip + sp + imd)
        self.quarantine_till = 0 # cislo stepu, do ktereho je agent v karantene
        self.infectious_rate = 0 # koeficient infekcnosti agenta (alias ir), vychozi hodnota pri nakazeni je 1, muze se
        # ale snizit v zavislosti na epidemiologickych opatrenich (napr. rouska snizuje ir o 75%, pocita se vliv prostredi apod.)
        self.sickness_count = 0 # pocet prodelanych onemocneni covid19 v ramci simulace
        self.sickness_result = agent.sickness_result # vysledek onemocneni - vyleceni nebo exitus
        self.work_type = agent.work_type # typ pracovniho pomeru agenta - firma, skola, nebo domov
        self.coord_house_xgrid = agent.coord_house_xgrid # x-souradnice domova agenta v gridu
        self.coord_house_ygrid = agent.coord_house_ygrid # y-souradnice domova agenta v gridu
        self.coord_work_xgrid = agent.coord_work_xgrid # x-souradnice zamestnani agenta v gridu
        self.coord_work_ygrid = agent.coord_work_ygrid # y-souradnice zamestnani agenta v gridu
        self.route_plan = route_plan # tydenni pohybovy retezec agenta (list of tuples (step, place), kde place je 'D', 'W',...)
        self.current_place = route_plan[0] # aktualni typ lokace agenta ('D', 'W',...), rizeni prepoctu vlivu prostredi na ir

        self.tydenni_spotreba_cepovane = agent.tydenni_spotreba_cepovane # tydeni restauracni splavek agenta (cepovane)
        self.tydenni_spotreba_lahvove = agent.tydenni_spotreba_lahvove # tydeni lahvovy splavek agenta
        self.beers_per_hour = {} # prumerna hodinova sporeba agenta pri navsteve restaurace nebo domaci lednicky,
        # jde o dict s keys 'restaurace' (spotreba cepovaneho) a 'doma' (spotreba lahvoveho), pricemz hodnota je list
        # [prumerny hodinovy splavek, pocet useku (stepu) piti piva vypocitanych podle poctu lokaci D/R
        # v pohybovem retezci]

        self.tested = {'antigen': 0, 'pcr': 0} # pocet testu, ktere agent podstoupil
        self.tested_at_step = 0
        self.positive_test_at_step = 0
        self.smart_app_active = False # True znamena, ze dany uzivatel ma zapnutou aplikaci eRouska
        self.has_mask_till = 0 # nenulova hodnota znamena, ze dany agent nosi rousku (po vytrasovani) do daneho stepu

    def step(self):
        """
        Operace provadene v jednom stepu agenta (uvnitr behu modelu)
        :return:
        """
        if self.model.schedule.steps == 0:
            # v prvnim kroku modelu prepocitam tydenni (teoretickou) spotrebu cepovaneho piva u dospelych agentu.
            # Protoze jsou pohybove retezce konstantni, je konstantni i spotreba piva v prubehu casu.
            # Pokud agent onemocni, nebo jsou aplikovana opatreni lockdownu, karanteny apod., je pohybovy retezec
            # docasne zmenen - agent nekonzumuje obvykle mnozstvi piva (dle teoreticke tydenni spotreby) a rozdil
            # mezi aktualni a teoretickou spotrebou ukazuje vliv onemocneni nebo opatreni na spotrebu
            self.calc_beer_consumption()
        self.move()

    def calc_beer_consumption(self):
        """
        Prepocet pivni konzumace dle pohybove matice na tyden - vygenerovana pohybova matice je v celem behu konstantni,
        ale muze ji modifikovat prodelavane onemocneni nebo epidemiologicka opatreni (na teoretickou spotrebu to
        ale nema vliv)
        :return:
        """
        # prepocitam spotrebu cepovaneho piva na nasledujici tyden podle poctu navstev restauraci
        if self.age >= self.model.beer_age_limit:
            happy_hours = self.route_plan.to_list().count('R')
            if happy_hours and self.tydenni_spotreba_cepovane > 0:
                # mimo pivni spotreby ukladam i pocet useku pro piti na index 1, coz je ale pro R nepodstatne
                self.beers_per_hour['restaurace'] = [self.tydenni_spotreba_cepovane / happy_hours, happy_hours]
                if not self.model.df_agent_snapshot.empty:
                    self.model.df_agent_snapshot.at[self.unique_id, 'beers_per_hour']['restaurace'] = [self.tydenni_spotreba_cepovane / happy_hours, happy_hours]
            # a to same pro lahvove pivo popijene doma (pro potreby modelu nerozhoduje denni doba konzumace)
            happy_hours = self.route_plan.to_list().count('D')
            if happy_hours and self.tydenni_spotreba_lahvove > 0:
                # pro D index 1 ukazuje, kolik useku bylo planovano, v pripade lockdownu a poctu D nad plan tim zajistim,
                # ze se nezvysi spotreba kvuli vyssimu poctu kroku stravenych doma oproti route planu
                self.beers_per_hour['doma'] = [self.tydenni_spotreba_lahvove / happy_hours, happy_hours]
                if not self.model.df_agent_snapshot.empty:
                    self.model.df_agent_snapshot.at[self.unique_id, 'beers_per_hour']['doma'] = [self.tydenni_spotreba_lahvove / happy_hours, happy_hours]

    def is_evidently_ill(self, typ='all', sick_period='regular'):
        """
        Vraci True/False, pokud je agent aktualne v symptomaticke fazi onemocneni (iis>0 && step in (++sst..--rit))
        :param typ: 'all' vraci True pro libovolny sicktype asymp i symp agenta, 'asymptomatic' vraci True jen
        pro agenta se sicktype == asymptomatic a 'symptomatic' pro agenta se sicktype == mild nebo severe
        :param sick_period: regular znamena symptomatickou fazi, superspreader infekcni fazi pred projevenim priznaku
        :return: Boolean
        """
        if sick_period != 'superspreader':
            is_evidently_ill = self.infected_in_step > 0 and self.super_spreader_till < self.model.schedule.steps <= self.regular_illness_till
            if typ == 'symptomatic' and is_evidently_ill:
                return self.sicktype != 'asymptomatic'
            elif typ == 'asymptomatic' and is_evidently_ill:
                return self.sicktype == 'asymptomatic'
            else:
                return is_evidently_ill
        else:
            # v superspreader fazi je kazdy agent asymptomaticky, sicktype tedy neni treba resit
            return self.infected_in_step > 0 and self.non_infectious_till < self.model.schedule.steps <= self.super_spreader_till

    def beer_yourself(self, where='R'):
        """
        Agente, napij se...
        :param where: specifikace mista konzumace (R, nebo D) udava, jestli agent pije lahvove nebo cepovane,
        konzumace se zaznamena do dictionary - pro sledovani celkove konzumace v ruznych podminkach
        :return:
        """
        if self.age >= self.model.beer_age_limit and self.beers_per_hour and not self.is_evidently_ill(typ='symptomatic', sick_period='regular'):
            # nemocny agent po projeveni priznaku pivo nepije (da si radsi caj nebo fizak), asymptomatik to neresi...
            # a deti a nepijaci (self.beers_per_hour je empty dictionary) pivo nepiji vubec
            if where == 'R':
                # agent pivar/ka vypije každou hodinu určité množství piv - pocitano v pulitrech, resp. lahvich,
                # prepocet hodinoveho splavku je relizovan na pocatku simulace podle planovaneho pohyboveho rezezce
                self.model.beer['cepovane'] += self.beers_per_hour['restaurace'][0]
            elif where == 'D':
                # v lokalite D pije agent lahvove
                self.model.beer['lahvove'] += self.beers_per_hour['doma'][0]

    def heal_yourself(self):
        """
        Vyleceni = prenastaveni indexu nemoci do vychoziho (zdraveho stavu), zustava jen immune_till udavajici cislo
        stepu, do ktereho trva munita, infected_in_step pro test podminek a zvysi se citac prodelanych onemocneni
        :return:
        """
        self.regular_illness_till = 0
        self.non_infectious_till = 0
        self.super_spreader_till = 0
        self.infectious_rate = 0
        self.positive_test_at_step = 0
        self.sickness_count += 1
        if not self.model.df_agent_snapshot.empty:
            self.model.df_agent_snapshot.loc[self.unique_id, ['regular_illness_till', 'non_infectious_till', 'super_spreader_till',
                                                  'infectious_rate', 'positive_test_at_step']] = 0
            self.model.df_agent_snapshot.at[self.unique_id, 'sickness_count'] += 1

    def mask_yourself(self, duration=0):
        """
        Agent zacne nosit rousku a nosi ji po dobu danou parametrem duration nebo smart_app_duration, pokud je
        aktivni opatreni eRousky
        :param: duration = trvani opatreni noseni rousky (pokud je aktivni precaution_smart_app, jakakoliv hodnota
        duration je ignorovana)
        :return:
        """
        if self.model.precaution_smart_app['is_active']:
            has_mask_till = self.model.schedule.steps + self.model.precaution_smart_app['smart_action_duration']
        else:
            has_mask_till = self.model.schedule.steps + duration
        if has_mask_till > self.model.schedule.steps:
            self.has_mask_till = has_mask_till
            if not self.model.df_agent_snapshot.empty:
                self.model.df_agent_snapshot.at[self.unique_id, 'has_mask_till'] = has_mask_till

    def demask_yourself(self):
        """
        Agent prestane nosit rousku
        :return:
        """
        self.has_mask_till = 0
        if not self.model.df_agent_snapshot.empty:
            self.model.df_agent_snapshot.at[self.unique_id, 'has_mask_till'] = 0

    def test_yourself(self):
        '''
        Testovani agenta na infekci - nakazeny agent obdrzi pozitivni vysledek na zaklade presnosti testu (falesne
        negativni vysledky maji urcitou pravdepodobnost vyskytu) a jen v obdobi, kdy vylucuje virus
        :return:
        '''
        test_type_index = 1 if 'pcr' in self.model.precaution_test['name'] else 0
        if (self.is_evidently_ill() or self.is_evidently_ill(sick_period='superspreader')) and \
                self.model.precaution_test['accuracy'][test_type_index] >= random.random():
            self.positive_test_at_step = self.model.schedule.steps + self.model.precaution_test['wait_till_result'][test_type_index]
            self.model.tested_agents['positive'] += 1
            if not self.model.df_agent_snapshot.empty:
                self.model.df_agent_snapshot.at[self.unique_id, 'positive_test_at_step'] = self.model.schedule.steps + self.model.precaution_test['wait_till_result'][test_type_index]
        else:
            self.model.tested_agents['negative'] += 1
        self.tested_at_step = self.model.schedule.steps
        if not self.model.df_agent_snapshot.empty:
            self.model.df_agent_snapshot.at[self.unique_id, 'tested_at_step'] = self.model.schedule.steps

    def quarantinize_yourself(self):
        self.quarantine_till = self.model.schedule.steps + self.model.precaution_quarantine['min_duration_in_steps']
        if not self.model.df_agent_snapshot.empty:
            self.model.df_agent_snapshot.at[self.unique_id, 'quarantine_till'] = self.model.schedule.steps + self.model.precaution_quarantine['min_duration_in_steps']

    def dequarantinize_yourself(self):
        self.quarantine_till = 0
        if not self.model.df_agent_snapshot.empty:
            self.model.df_agent_snapshot.at[self.unique_id, 'quarantine_till'] = 0

    def suspiciousize_yourself(self):
        '''
        Po vyvanuti imunity je agent opet nachylny k infekci - resetovana je i vlastnost infected_in_step pouzivana
        po test infikovatelnosti nebo nemoci
        :return:
        '''
        self.immune_till = 0
        self.infected_in_step = 0
        self.positive_test_at_step = 0
        if not self.model.df_agent_snapshot.empty:
            self.model.df_agent_snapshot.at[self.unique_id, ['immune_till', 'infected_in_step', 'positive_test_at_step']] = 0

    def calc_infect_rate(self):
        '''
        Prepocet koeficientu infekcnosti (infectious_rate, resp. ir)
        :return:
        '''
        # pomocne aliasy - kod pak neni tak dlouhy
        rit = self.regular_illness_till
        sst = self.super_spreader_till

        if self.is_evidently_ill():
            # pokud je agent v regulerni (symptomaticke) fazi nemoci, ir linearne klesa (i pro asym prubeh)
            self.infectious_rate = (rit-self.model.schedule.steps) / (rit-sst)
        elif self.is_evidently_ill(sick_period='superspreader'):
            # pokud je agent ve fazi superprenasece (cast obdobi pred projevenim priznaku), je ir maximalni
            self.infectious_rate = 1
        else:
            # pokud je agent mimo obdobi superprenasece nebo regulerni nemoci, neni infekcni (imunita po nemoci,
            # nebo jeste nevylucuje virove partikule)
            self.infectious_rate = 0

        if self.infectious_rate > 0:
            min_age = int(self.model.precaution_mask['applicable_age_categ'].split('-')[0])
            if (self.model.precaution_mask['is_active'] and int(self.age) >= int(min_age)) or (self.has_mask_till >= self.model.schedule.steps):
                # pokud je aktivni opatreni ochrany dychacich cest (ODD), zmensim ir o protektivni ucinek OOD a zapocitam
                # i vliv prostredi podle aktualni lokace agenta
                self.infectious_rate *= (1 - self.model.precaution_mask['base_protective_value']*self.model.precaution_mask['protection'][self.current_place])
            if self.current_place == 'P':
                # uprava prenosu onemocneni v Parcich/Prirode, kde je riziko infekce minimalni i pri neaktivni ODD
                self.infectious_rate *= 0.1

        if not self.model.df_agent_snapshot.empty:
            self.model.df_agent_snapshot.at[self.unique_id, 'infectious_rate'] = self.infectious_rate
        return self.infectious_rate

    def calc_infect_periods(self, step_nr=None):
        '''
        prepocet cisel stepu, ve kterych se meni charakter onemocneni, aplikuje se pri nakazeni agenta. Uvedena metoda
        zvysuje prehlednost kodu...mam ten pocit...
        :param step_nr: cislo aktualniho stepu
        :return:
        '''
        step_nr = self.model.schedule.steps if not step_nr else step_nr
        if self.sickness_count > 0:
            # jedna se o opakovanou nakazu - prepocitam charakteristiku onemocneni agenta nahodnym vyberem ze skupiny
            # agentu stejne vekove kategorie a pohlavi (sample je nahodny vyber 1 zaznamu, reset_index kvuli at)
            sick_template = self.model.df_agents.loc[
                (self.model.df_agents['age_categ']==self.age_categ) & (self.model.df_agents['sex']==self.sex)].sample().reset_index()
            self.immunity_duration = sick_template.at[0, 'immunity_duration']
            self.inkubation_period = sick_template.at[0, 'inkubation_period']
            self.sickness_period = sick_template.at[0, 'sickness_period']
            self.sickness_result = sick_template.at[0, 'sickness_result']
            self.sicktype = sick_template.at[0, 'sicktype']
            self.spreader_period_from = sick_template.at[0, 'spreader_period_from']
        self.infected_in_step = step_nr
        self.non_infectious_till = step_nr + self.inkubation_period - self.spreader_period_from
        self.super_spreader_till = step_nr + self.inkubation_period
        self.regular_illness_till = step_nr + self.inkubation_period + self.sickness_period
        self.immune_till = step_nr + self.inkubation_period + self.sickness_period + self.immunity_duration
        self.sickness_count += 1

        if not self.model.df_agent_snapshot.empty:
            self.model.df_agent_snapshot.loc[
                self.unique_id,
                ['infected_in_step', 'non_infectious_till', 'super_spreader_till', 'regular_illness_till', 'immune_till']
            ] = [step_nr, self.non_infectious_till, self.super_spreader_till, self.regular_illness_till, self.immune_till]
            self.model.df_agent_snapshot.at[self.unique_id, 'sickness_count'] += 1

    def move(self):
        '''
        implementace kroku agenta
        :return:
        '''
        # route_coord obsahuje index z listu route_plan odpovidajici hodine stepu
        route_coord = self.model.schedule.steps % len(self.route_plan)
        place_to_move = self.route_plan[route_coord]
        unscheduled_home = False

        if self.is_evidently_ill(typ='symptomatic', sick_period='regular') and self.sicktype == 'severe':
            # nemocny agent s prubehem severe je po projeveni priznaku hospitalizovan v nemocnici do vyleceni
            place_to_move = 'H'
        elif self.quarantine_till >= self.model.schedule.steps:
            # jakykoliv agent s nastavenou karantenou zustava doma - jde o prubeh mild po projeveni priznaku,
            # vsechny nakazene agenty zachycene testovanim (s vyjimkou prubehu severe)
            if place_to_move != 'D':
                # agent mel puvodne namireno jinam, zmenu musim poznacit, abych zajistil nezvyseni spotreby lahvacu pri neplanovanych
                unscheduled_home = True
            place_to_move = 'D'
        elif self.model.simtype == 'covid' and place_to_move in ('R', 'N'):
            # pokud se otevrene siri epidemie, budou se agenti snazit vyhnout riziku nakazy ve zbytnych lokacich - snaha
            # bude tim vetsi, cim vice nemocnych nebo pozitivne testovanych agentu bude model obsahovat a cim starsi
            # je agent (agent vi, ze s poctem nakazenych roste pravdepodobnost infikace a s vekem i riziko vaznejsiho
            # prubehu a radeji tedy zustane doma)
            p = self.model.get_threshold() * self.model.agent_age_categs.index(self.age_categ) / (2 * self.model.df_agent_snapshot.shape[0])
            if p < random.random():
                unscheduled_home = True
                place_to_move = 'D'

        elif self.model.precaution_lockdown['is_active']:
            # pokud agent neni nemocny ani v karantene, pak kontroluji sektorova omezeni nebo lockdown
            if 'R' in self.model.precaution_lockdown['closed_locations'] and place_to_move == 'R':
                # sektorove uzavreni restauraci - agenti vyberou nahradni lokaci (domu, do prirody nebo na nakup)
                random_place = self.random.choice(['D', 'P', 'N'])
                if random_place == 'D':
                    unscheduled_home = True
                place_to_move = random_place
            if 'W' in self.model.precaution_lockdown['closed_locations'] and place_to_move == 'W':
                # sektorove uzavreni firem - agenti vyberou nahradni lokaci (domu, do prirody nebo na nakup)
                random_place = self.random.choice(['D', 'P', 'N'])
                if random_place == 'D':
                    unscheduled_home = True
                place_to_move = random_place
            if 'S' in self.model.precaution_lockdown['closed_locations'] and place_to_move == 'S':
                # sektorove uzavreni skol - agenti vyberou nahradni lokaci (s nejvetsi pravdepodonosti domu, obcas i do prirody nebo na nakup)
                random_place = self.random.choice(['D', 'P', 'D', 'N', 'D'])
                if random_place == 'D':
                    unscheduled_home = True
                place_to_move = random_place

        #if place_to_move == 'D' and self.beers_per_hour and home_beer > 0:
            # u destinace D snizim limit zbyvajicich pivnich useku o 0.66..1 - pokud bych to neudelal, budou agenti pit
            # pri neplanovanych D prumerne mnozstvi lahvacu a celkova spotreba se umele zvysi (vychazim z predpokladu
            # ze agenti nahrazuji lahvaci cepovane jen v omezenem mnozstvi)
        #    self.model.beers_per_hour['doma'][1] -= self.random.uniform(0.66, 1.0)

        # zpracovani pohybu agenta podle matice mobility, nebo podle vysledku opatreni a stavu agenta
        if place_to_move != self.current_place:
            if place_to_move == 'S':
                n = 0
            if place_to_move == 'D':
                # destination je tuple s koordinaty (x,y) nove lokace
                destination = (self.coord_house_xgrid, self.coord_house_ygrid)
            elif place_to_move == 'W':
                destination = (self.coord_work_xgrid, self.coord_work_ygrid)
            elif place_to_move == 'N':
                # random vyber nakupni lokace
                destination = self.random.sample(self.model.places['shops'], 1)[0]
            elif place_to_move == 'R':
                # random vyber restaurace
                destination = self.random.sample(self.model.places['pubs'], 1)[0]
            elif place_to_move == 'P':
                # random vyber parku nebo prirodni lokality
                destination = self.random.sample(self.model.places['nature'], 1)[0]
            else:
                # zbyva posledni moznost, kdy place_to_move == 'H' (random pro pripad, ze by v modelu bylo vic H)
                destination = self.random.sample(self.model.places['hospital'], 1)[0]
            # agent se presunuje na cilovou lokaci a preulozi se oznaceni aktualni pozice
            self.model.grid.move_agent(self, (int(destination[0]), int(destination[1])))
            self.current_place = place_to_move
            if not self.model.df_agent_snapshot.empty:
                self.model.df_agent_snapshot.loc[self.unique_id, 'current_place'] = place_to_move
                # DevNote: pro vlozeni tuple/list musim pouzit at misto loc - loc je multirow modifikace a vyhazuje
                # "ValueError: Must have equal len keys and value when setting with an iterable" i se single row
                # (viz. numpy repr.), index a unique_id je ve snapshotu to same, takze je at OK
                self.model.df_agent_snapshot.at[self.unique_id, 'pos'] = tuple(map(lambda q: int(q), destination)) #f'{int(destination[0])},{int(destination[1])}' #tuple(int(destination[0]), int(destination[1]))
        if place_to_move == 'D' and unscheduled_home:
            # pokud je agent doma neplanovane (karantena, lockdown,...), lahvace nepije
            # TODO: aplikovat nahradni pijaky podle klice pivo z Generatoru
            x = 1
        else:
            self.beer_yourself(where=place_to_move)

class BeerModel(Model):
    """
    Model class:
    -> model world with agents living in
    """

    def __init__(self, data_path = None, simtype = 'covid', random_seed = 42, max_steps = 17520,
                 precautions=[]):
        # super constructor, agents number is new instance variable
        # inherrited: running (Boolean), current_id (int)
        super().__init__()
        self.reset_randomizer(random_seed)
        self.random.seed(random_seed)
        self.running = True

        self.data_path = os.path.join(os.getcwd(), 'data') if not data_path else data_path # cesta ke slozce zdroju a vystupu
        self.max_steps = max_steps # uvazovany pocet stepu
        self.beer_age_limit = 18 # vek, od ktereho agent muze konzumovat pivo
        # nactu agenty generovane v csv a jejich route plan; protoze dataframe pouzivam pri reinfekcich, je pod self
        self.df_agents = pd.read_csv(os.path.join(self.data_path, 'source/df_agents.csv'), sep=';', index_col=[0]) # dataframe agentu ze souboru Generatoru
        self.agent_age_categs = list(self.df_agents['age_categ'].unique()) # list vekovych kategorii vyuzitych v modelu
        df_agent_moves = pd.read_csv(os.path.join(self.data_path, 'source/df_agent_moves.csv'), sep=';', index_col=['agent_id']) # dataframe retezcu mobility jednotlivych agentu

        # definice simulacniho sveta
        self.grid_map = pd.read_csv(os.path.join(self.data_path, 'source/df_grid.csv'), sep=';', index_col=[0]) # nacteni mapy sveta s definici lokaci
        self.width = self.grid_map.shape[1] # sirka sveta
        self.height = self.grid_map.shape[0] # vyska sveta

        # define multigrid toroidal environment
        self.grid = MultiGrid(self.width, self.height, True)
        # prevedeni 2D vektoru na 1D (itertools je rychlejsi nez vnorene cykly)
        place_list = list(itertools.chain(*self.grid_map.values.tolist()))
        # stringove reprezentace prevedu na slovniky
        place_list = [ast.literal_eval(place) for place in place_list]
        self.places = {
            'houses': [],
            'workplaces': [],
            'schools': [],
            'nature': [],
            'pubs': [],
            'shops': [],
            'hospital': []
        }
        for place in place_list:
            key = list(place.keys())[0]
            value = list(place.values())[0]
            # klic obsahuje sekvenci vyznamu mista (napr. WN pro nakupni centrum)
            if 'D' in key:
                self.places['houses'].append(value)
            if 'W' in key:
                self.places['workplaces'].append(value)
            if 'S' in key:
                self.places['schools'].append(value)
            if 'P' in key:
                self.places['nature'].append(value)
            if 'R' in key:
                self.places['pubs'].append(value)
            if 'N' in key:
                self.places['shops'].append(value)
            if 'H' in key:
                self.places['hospital'].append(value)

        # vytvoreni novych agentu a umisteni do modelu
        self.agents = []
        self.df_deaths = pd.DataFrame()
        for agent in self.df_agents.itertuples():
            route_plan = df_agent_moves.loc[agent.Index]
            self.agents.append(BeerAgent(agent, self, route_plan))
            #if agent.tydenni_spotreba_cepovane > 0:
            #    self.agents[-1].beer_per_hour = df_agent_moves.loc[agent.Index]

        # mnozstvi vypiteho piva
        self.beer = {
            'cepovane': 0,
            'lahvove': 0
        }

        self.simtype = simtype #'covid', 'no_covid'
        self.precautions = precautions # seznam opatreni, ktera maji byt v modelu aplikovana
        if self.precautions:
            self.precautions = [self.precautions.lower()] if ',' not in self.precautions \
                else [p.strip().lower() for p in self.precautions.split(',')]
        self.base_P = 0.02
        self.tested_agents = {'positive': 0, 'negative': 0}
        #self.quarantinized_agents = 0

        self.df_results = pd.DataFrame()
        self.df_infected_agents = pd.DataFrame()
        self.df_smart_contacts = pd.DataFrame()
        self.df_agent_snapshot = pd.DataFrame()
        #self.df_agents = pd.DataFrame()

        # define scheduler and link it to model
        self.schedule = RandomActivation(self)
        # place agents to grid cells
        #position_stack = {'x': [], 'y': []}
        for agent in self.agents:
            #a = agent.coord_house_xgrid
            self.grid.place_agent(agent, (int(agent.coord_house_xgrid), int(agent.coord_house_ygrid)))
            #self.grid.place_agent(agent, (int(agent.coord_house_xgrid), int(agent.coord_house_ygrid)))
            self.schedule.add(agent)
        if simtype == 'covid':
            # TODO: vybrat asymptomatickeho prenasece
            # v simulaci s infekci vyberu na pocatku jednoho agenta pro infikaci
            patient_0 = self.random.choice(self.schedule.agents)
            patient_0.calc_infect_periods(1)
            patient_0.infected_by = [-1]
            self.save_infected_agent(patient_0, np.nan, place='Ext')

        # vycet opatreni - kazde opareni je dictionary
        with open(os.path.join(data_path, 'source\config_sim.json')) as file:
            data = json.loads(file.read())

        self.precaution_mask = {
            # aplikace ochrany dychacich cest
            'name': data['mask']['nazev'],
            # vekove rozmezi, pro ktere je opatreni aplikovatelne
            'applicable_age_categ': data['mask']['aplikovatelne_pro_vek'],
            # hranice pro aktivaci opatreni - trigger_threshold je bud pocet symptomatickych nemocnych,
            # nebo pocet pozitivne testovanych (vzdy klouzave kumulativne za 7 dnu zpetne), dosazeni hranice
            # trigger_threshold pri aktivovanem opatreni dane opatreni opet deaktivuje
            # (TODO tip: trigger_threshold_start, trigger_threshold_end pro ruzne podminky aktivace a deaktivace u vsech precs)
            'trigger_threshold': data['smart_app']['minimalni_trvani_dnu'] if data['smart_app']['minimalni_trvani_dnu'] != 'max' else self.max_steps+1,
            # minimalni trvani aktivovaneho opatreni i kdyby podminky odpovidaly stavu pro deaktivaci
            'min_duration_in_steps': data['mask']['minimalni_trvani_dnu'] * 24,
            # cislo stepu pro ukonceni opatreni (+1), dopocitana hodnota pri aktivaci
            'stop_precaution_at': 0,
            # pocet aktivaci opatreni v prubehu simulace
            'chapters': 0,
            # uprava base_protective_value podle prostredi (ir(agent)=ir*(1-bpv*p(loc))), definuji tedy ucinky prostredi
            # jako dictionary. Pro Park/Prirodu je riziko prenosu minimalni, ir tedy bude velmi nizke (prepocet
            # ale probiha na jinem miste). V Restauraci nebo Doma je riziko prenosu vyssi kvuli obtiznosti dodrzovani
            # opatreni ODD a parametrum prostredi (uzavrene). Protektivni ucinek ODD se nezmeni na Pracovisti/Skole (W),
            # ani na Nakupech - na tech mistech v modelu predpokladam 100% dodrzovani opatreni po celou dobu pobytu.
            # Parametr ir v Nemocnici (H) je prozatim irelevantni, protoze model nepocita s vlivem onemocneni
            # na zdravotni personal a kapacitu zdravotniho systemu.
            # Idealni pripad pocita s hodnotou 1 u vsech kategorii
            'protection': data['mask']['ucinnost_dle_lokace'],
            # hodnota ochrany pro vnitrni prostory - ucinnost rousky
            'base_protective_value': data['mask']['ochrana'],
            # hodnota True je nastavena, pokud je opatreni aktivni
            'is_active': False
        }
        self.precaution_lockdown = {
            # lockdown nebo sektorove omezeni, lisi se vyctem uzavrenych lokaci
            'name': data['sector']['nazev'],
            # TODO tip: uvedenim jineho rozsahu min-max u applicable_age_categ lze simulovat ochranu zranitelnych skupin
            #  (seniori)...otazkou je, zda to ma vubec cenu, kdyz i jine modely (a nakonec i realita) ukazuji na nefunkcnost omezeni...
            'applicable_age_categ': data['sector']['aplikovatelne_pro_vek'],
            'trigger_threshold': data['sector']['mez_aktivace_deaktivace'],
            'min_duration_in_steps': data['sector']['minimalni_trvani_dnu'] * 24 if data['sector']['minimalni_trvani_dnu'] != 'max' else self.max_steps+1 * 24,
            'stop_precaution_at': 0,
            'chapters': 0,
            # seznam uzavrenych lokaci, R = sector_pub, W = workplace + school, N = nakupni zona, 'P' = zakaz vychazeni,
            # pro uplny lockdown uvedu vsechny lokace ['R', 'W', 'N', 'P']
            'closed_locations': data['sector']['uzavrene_lokace'],
            'is_active': False
        }
        self.precaution_smart_app = {
            # chytra aplikace - eRouska (evidence kontaktu mezi uzivateli aplikace/tokenu),
            # prideleni aplikaci v 1. kroku modelu, kontakty se ukladaji na konci kroku modelu, 5-ti denni historie
            'name': data['smart_app']['nazev'],
            # penetration predstavuje rozdeleni aplikaci ve vekovych skupinach, de facto nahrazuje applicable_age_categ
            'penetration': data['smart_app']['podil_aplikaci_v_kategorii'],
            #'penetration': pd.read_csv(os.path.join(self.data_path, 'source/precautions/smart_app.csv'), sep=';'),
            'trigger_threshold': data['smart_app']['mez_aktivace_deaktivace'],
            # jakmile je opatreni eRousky spusteno, bezi do konce simulace
            'min_duration_in_steps': data['smart_app']['minimalni_trvani_dnu'] * 24 if data['smart_app']['minimalni_trvani_dnu'] != 'max' else self.max_steps+1,
            'stop_precaution_at': 0,
            'chapters': 0,
            # smart action definuje, co se stane po odhaleni pozitivniho/nemocneho kontaktu, muze nabyvat hodnot
            # Q=karantena, QD=karantena na celou domacnost, T=test, M=rouska, MD=rouska pro celou domacnost
            'smart_action': data['smart_app']['akce'],
            # kolik rizikovych kontaktu nasleduje smart_action (eRouska je anonymni a kontakty nelze identifikovat - dodrzovani je dobrovolne)
            'smart_action_prob': data['smart_app']['efektivita_aplikace'],
            # trvani individualniho opatreni po vytrasovani (aplikovano jen u Q, QD, M a MD)
            'smart_action_duration': data['smart_app']['minimalni_trvani_chytre_akce_dnu'] * 24,
            'delete_db_after': data['smart_app']['kontakty_uchovavat_dnu'] * 24,
            'is_active': False
        }
        self.precaution_quarantine = {
            # aplikovano na agenta ve chvili testu, symptomatickeho onemocneni nebo sdileni domacnosti
            'name': data['karantena']['nazev'],
            'applicable_age_categ': data['karantena']['cilova_vekova_skupina'],
            'trigger_threshold': data['karantena']['mez_aktivace_deaktivace'],
            'min_duration_in_steps': data['karantena']['minimalni_trvani_dnu'] * 24,
            'stop_precaution_at': 0,
            'chapters': 0,
            # D = karantena pro spolecnou domacnost, W = pracovni a skolni kol.
            'quarantine_type': data['karantena']['typ_karanteny'],
            'is_active': False
        }
        self.precaution_test = {
            'name': data['test']['nazev'],
            'test_type': data['test']['typ_testu'], #['antigen', 'pcr'],
            # zpozdeni mezi provedenim testu a vysledkem (pri nenulove hodnote se posune detekce do budoucnosti)
            'wait_till_result': data['test']['zpozdeni_vysledku_hodin'], # [0, 12], # 0 pro antigen, 12 pro pcr
            # jak casto lze za normalnich okolnosti absolvovat test (testovani u eRousky muze mit kratsi interval)
            'frequency_once_per_days': data['test']['frekvence_testu_1_krat_za_dny'], #[3, 7], # jednou za 3 dny antigen, jednou za 5 dni PCR
            # senzitivita testu - kolik nakazenych dokaze identifikovat (1-accuracy = pomer falesne negativnich testu)
            'accuracy': data['test']['presnost'], # [0.7, 0.99], # 70% presnost u antigenu, 99% presnost u PCR
            'applicable_age_categ': data['test']['aplikovatelne_pro_vek'],
            # nulovy threshold znamena aktivaci opatreni hned v uvodu simulace
            'trigger_threshold': data['test']['mez_aktivace_deaktivace'],
            'min_duration_in_steps': data['test']['minimalni_trvani_dnu'] * 24,
            'stop_precaution_at': 0,
            'chapters': 0,
            # seznam lokaci, na kterych probiha testovani - W = skoly a pracoviste, D =  doma (nebo odberova mista)
            'test_places': data['test']['testovaci_lokace'],
            'is_active': False
        }
        self.applied_precautions = [] # seznam aplikovanych opatreni pro dany beh simulace
        # citace neuspesnych a uspesnych pokusu o infikaci
        self.a_not_infected = 0
        self.a_newly_infected = 0

    def agents_to_dataframe(self):
        '''
        Vytvoreni dataframe s agenty a jejich daty (v prvnim kroku simulace), nad timto dataframe pak probihaji
        vsechny operace v ramci simulace a podle nej i upravy mesa agentu - upravuji se jen ti mesa agenti,
        u nichz doslo ke zmene, aniz by se musela prochazet cela popuace v cyklu (uspora vypocetniho casu, navic i v
        pripade cyklu by bylo treba ukadat pomocne promenne do vars, dicts apod...df by i tedy v pripade for cykly
        stale byl relevantnim ulozistem mezivysledku).
        Dataframe je mozne ziskat i z datacollectoru (agent_vars po prislusnem nastaveni), jenze df v takovem pripade
        obsahuje vechny kroky simulace a s velikosti df tak lin. roste i casova narocnost behu datacollectoru
        (rozdil 24h a 30min cekani na vysledek behu simulace uz je celkem znat). V reseni s vlastnim df nastavenym
        na pocatku je casove narocny jen prvni krok.
        :return:
        '''
        for agent in self.agents:
            self.df_agent_snapshot = self.df_agent_snapshot.append(agent.__dict__, ignore_index=True)
        self.df_agent_snapshot['unique_id'] = self.df_agent_snapshot['unique_id'].astype(int)
        self.df_agent_snapshot.set_index('unique_id', inplace=True, drop=False)
        for agent in self.agents:
            # uvodni nastaveni pivniho splavku (pro dobu, kdy je svet v poradku)
            agent.calc_beer_consumption()

    def set_applied_precautions(self):
        """
        Protiopatreni v atributech BeerModelu jsou nastavena jako aplikovana vlozenim do applied_precautions - model
        pak pocita jen s opatrenimi a konfiguracemi, ktere byly zadany uzivatelem
        :return:
        """
        # lockdown nema implementovane options - je bud off, nebo on, ale muze mit upravenu hodnotu trigger_threshold
        lockdown = [p for p in self.precautions if p.startswith('lockdown')]
        if lockdown:
            if '!' in lockdown[0] and lockdown[0].index('!') < len(lockdown[0])-1:
                # prahova hodnota pro spusteni opatreni je uvedena na konci nazvu opatreni za znakem vykricniku (pokud
                # hodnota a "!" uveden neni, pouzije se vychozi hodnota v opatreni)
                self.precaution_lockdown['trigger_threshold'] = int(lockdown[0][lockdown[0].index('!')+1:])
            self.applied_precautions.append(self.precaution_lockdown)
            # lockdown je vlastne nejsirsi sektorove omezeni s uzavrenim vsech lokaci mimo lokace D
            self.precaution_lockdown['closed_locations'] = ['R', 'W', 'N', 'P', 'S']
        # ostatni opatreni maji ruzne volby...
        # existuje pozadavek na upravu opatreni ochrany dychacich cest?
        mask = [p for p in self.precautions if p.startswith('mask')]
        if mask:
            if '!' in mask[0] and mask[0].index('!') < len(mask[0])-1:
                self.precaution_mask['trigger_threshold'] = int(mask[0][mask[0].index('!')+1:])
            # opatreni muze mit ruzne volby (za podtrzitkem); pokud je nema, je pouzito defaultni nastaveni
            options = mask[0].split('_')[1] if '_' in mask[0] else ''
            if options:
                if 'i' in options:
                    # model pocita s idealnim nosenim rousek bez vlivu prostredi (100% nasazeni ve vsech prostredich)
                    self.precaution_mask['protection'] = {'D': 1, 'W': 1, 'S': 1, 'P': 1, 'R': 1, 'N': 1, 'H': 1}
                    self.precaution_mask['name'] += '-idealistic'
            # pridani nastaveneho opatreni k aplikovanym, spusteno bude pri dosazeni sveho thresholdu
            self.applied_precautions.append(self.precaution_mask)
        # existuje pozadavek na testovaci opatreni?
        test = [p for p in self.precautions if p.startswith('test')]
        if test:
            if '!' in test[0] and test[0].index('!') < len(test[0])-1:
                self.precaution_test['trigger_threshold'] = int(test[0][test[0].index('!')+1:])
            # opatreni muze mit ruzne volby (za podtrzitkem); pokud je nema, je pouzito defaultni nastaveni
            options = test[0].split('_')[1] if '_' in test[0] else ''
            if options:
                self.precaution_test['test_places'] = []
                if 'w' in options:
                    # testovani na pracovistich a ve skolach
                    self.precaution_test['test_places'].append('W')
                    self.precaution_test['name'] += '-work-school'
                if 'd' in options:
                    # samostesty/odberova mista pro agenty "mimo system" skoly a prace
                    self.precaution_test['test_places'].append('D')
                    self.precaution_test['name'] += '-home'
                if 'p' in options:
                    # je aplikovan PCR test misto antigenniho
                    self.precaution_test['name'] += '-pcr'
                # odstraneni pripadnych duplicit (fungovalo by to i tak, ale...)
                self.precaution_test['test_places'] = list(set(self.precaution_test['test_places']))
            # seznam testovacich mist musi mit alespon jednu hodnotu, jinak jde o chybu (napr. nespravne parametry v batch runneru)
            assert len(self.precaution_test['test_places']) > 0, f'PRECAUTION ERROR (test): incorrect precaution type in {self.precautions} or default value missing in __init__ -> test_places not set!'
            # pridani nastaveneho opatreni k aplikovanym, spusteno bude pri dosazeni sveho thresholdu
            self.applied_precautions.append(self.precaution_test)
        # existuje pozadavek na karanteni opatreni?
        quarantine = [p for p in self.precautions if p.startswith('quarantine')]
        if quarantine:
            if '!' in quarantine[0] and quarantine[0].index('!') < len(quarantine[0])-1:
                self.precaution_quarantine['trigger_threshold'] = int(quarantine[0][quarantine[0].index('!')+1:])
            options = quarantine[0].split('_')[1] if '_' in quarantine[0] else ''
            if options:
                self.precaution_quarantine['quarantine_type'] = []
                if 'd' in options:
                    # karantena na spolecnou domacnost nakazeneho/pozitivne testovaneho
                    self.precaution_quarantine['quarantine_type'].append('D')
                    self.precaution_quarantine['name'] += '-household'
                if 'w' in options:
                    # karantena na spolecne pracoviste/skolu
                    self.precaution_quarantine['quarantine_type'].append('W')
                    self.precaution_quarantine['name'] += '-work-school'
                self.precaution_quarantine['quarantine_type'] = list(set(self.precaution_quarantine['quarantine_type']))
            assert len(self.precaution_quarantine['quarantine_type']) > 0, f'PRECAUTION ERROR (quarantine): incorrect precaution type in {self.precautions} or default value missing in __init__ -> quarantine_type not set!'
            self.applied_precautions.append(self.precaution_quarantine)
        # existuje pozadavek na sektorova opatreni?
        # NOTE: sektorova omezeni a lockdown se uz z definice vylucuji (lockdown je master)
        sector = [p for p in self.precautions if p.startswith('sector')]
        if sector and not [p for p in self.precautions if p.startswith('lockdown')]:
            if '!' in sector[0] and sector[0].index('!') < len(sector[0])-1:
                self.precaution_lockdown['trigger_threshold'] = int(sector[0][sector[0].index('!')+1:])
            options = sector[0].split('_')[1] if '_' in sector[0] else ''
            if options:
                self.precaution_lockdown['closed_locations'] = []
                if 'r' in options:
                    # uzavreni restauraci
                    self.precaution_lockdown['closed_locations'].append('R')
                    self.precaution_lockdown['name'] += '-restaurants'
                if 'w' in options:
                    # uzavreni pracovist a skol
                    self.precaution_lockdown['closed_locations'].append('W')
                    self.precaution_lockdown['name'] += '-work-school'
                self.precaution_lockdown['closed_locations'] = list(set(self.precaution_lockdown['closed_locations']))
                if not self.precaution_lockdown['closed_locations']:
                    self.precaution_lockdown['closed_locations'] = ['R']
                    self.precaution_lockdown['name'] += '-restaurants'
            assert len(self.precaution_lockdown['closed_locations']) > 0, f'PRECAUTION ERROR (lockdown/sector): incorrect precaution type in {self.precautions} or default value missing in __init__ -> closed_locations not set!'
            self.applied_precautions.append(self.precaution_lockdown)
        # existuje pozadavek na aplikaci eRousky?
        app = [p for p in self.precautions if p.startswith('app')]
        if app:
            if '!' in app[0] and app[0].index('!') < len(app[0])-1:
                self.precaution_smart_app['trigger_threshold'] = int(app[0][app[0].index('!')+1:])
            options = app[0].split('_')[1] if '_' in app[0] else ''
            if options:
                self.precaution_smart_app['smart_action'] = []
                if 'i' in options:
                    # idealni stav - 100% pokryti populace aplikaci/tokenem
                    self.precaution_smart_app['penetration']['podil_aplikaci'] = 1.0
                    self.precaution_smart_app['name'] += '-idealistic'
                if 'qd' in options:
                    # cela domacnost smart kontaktu pozitivniho/nemocneho agenta podstoupi karantenu
                    self.precaution_smart_app['smart_action'].append('QD')
                    self.precaution_smart_app['name'] += '-quarantine2household'
                elif 'q' in options:
                    # smart kontakty pozitivniho/nemocneho agenta podstoupi karantenu (Q xor QD)
                    self.precaution_smart_app['smart_action'].append('Q')
                    self.precaution_smart_app['name'] += '-quarantine'
                if 't' in options:
                    # smart kontakty pozitivniho/nemocneho agenta podstoupi test
                    self.precaution_smart_app['smart_action'].append('T')
                    self.precaution_smart_app['name'] += '-test'
                if 'md' in options:
                    # cela domacnost smart kontaktu pozitivniho/nemocneho agenta nasadi rousky
                    self.precaution_smart_app['smart_action'].append('MD')
                    self.precaution_smart_app['name'] += '-mask2household'
                elif 'm' in options:
                    # smart kontakty pozitivniho/nemocneho agenta nasadi rousky
                    self.precaution_smart_app['smart_action'].append('M')
                    self.precaution_smart_app['name'] += '-mask'
            self.applied_precautions.append(self.precaution_smart_app)
        # TODO tip: prehodit precautions do samostatne tridy, vyuzit dedicnost (lepsi rozsiritelnost)...ale az po obhajobe
        # TODO tip: upravit simulaci i pro scenare, kde se vyskytuje sector a lockdown s jinymi tt, napr.
        #  'app_tm!0,sector_r!10,lockdown!50', kde se aktualne spousti jen lockdown!50

    def distribute_smart_app(self):
        '''
        Pokud je eRouska soucasti simulace, pak provedu instalaci aplikaci do telefonu
        a/nebo rozdam Singapurske tokeny tem co telefon nemaji, vse podle rozdeleni technologii/ochoty v populaci
        :return:
        '''
        df_app_penetration = self.precaution_smart_app['penetration']
        for r in df_app_penetration.loc[(df_app_penetration['podil_aplikaci'] > 0)].itertuples():
            # zpracovavam jen vekove kategorie, ktere maji nenulovy podil appek
            mask_categ = (self.df_agent_snapshot['age'].between(int(r.kategorie.split('-')[0]), int(r.kategorie.split('-')[1])))
            # vyberu nahodny vzorek indexu z vekove kategorie pro zmenu smart_app_active na True
            smart_agents = self.df_agent_snapshot.loc[mask_categ].sample(frac=r.podil_aplikaci, random_state=seed).index
            # a instaluji aplikace/vesim na krk tokeny
            self.df_agent_snapshot.loc[smart_agents, 'smart_app_active'] = True
            for idx in smart_agents.to_list():
                # zmenu stavu provedu i v instancich agentu
                self.agents[idx]['smart_app_active'] = True

    def get_threshold(self):
        """
        Threshold je soucet pozitivne testovanych v poslednich 7 dnech (pokud je aktivni opatreni testovani
        nebo smart action testovani u eRousky) s poctem symptomaticky nemocnych v poslednich 7 dnech.
        :return: current_level je aktualni hodnota thresholdu
        """
        step = self.schedule.steps
        # ramec pro pocet testovanych musi zacinat od 1
        start_step = 1 if step < 169 else step - 169

        # pocet pozitivne testovanych za 7 poslednich dni (pokud neni opatreni testovani aktivni, je hodnota rovna 0)
        mask_positively_tested = (self.df_agent_snapshot['positive_test_at_step'].between(start_step,step-1))
        current_level = self.df_agent_snapshot.loc[mask_positively_tested].shape[0]

        # maska pro pocet symptomatickych nemocnych za poslednich 7 dni, finalni current_level je soucet obou hodnot
        mask_1st_step_in_bed = (self.df_agent_snapshot['super_spreader_till'] > 0) & \
                               (self.df_agent_snapshot['super_spreader_till'].between(start_step,step-1)) & \
                               (self.df_agent_snapshot['sicktype'].isin(['mild', 'severe']))

        # agenti, kteri meli pozitivni test a v poslednich 7 dnech se dostali do symptomaticke faze, musi byt odecteni
        # od mask_1st_step_in_bed, jinak by current_level obsahoval duplicity; metoda symmetric_difference provadi
        # XOR operaci pro sjednoceni indexu (bitwise operator ^ je v tomto pripade deprecated, tak jdu s dobou...)
        current_level += self.df_agent_snapshot.loc[mask_1st_step_in_bed].index.symmetric_difference(
            self.df_agent_snapshot.loc[mask_positively_tested].index
        ).shape[0]

        return current_level

    def calc_thresholds(self):
        '''
        Spousteni opatreni pri dosazeni thresholdu a vypinani opatreni po uklidneni situace. Threshold current_level
        je soucet pozitivne testovanych v poslednich 7 dnech (pokud je aktivni opatreni testovani nebo smart action
        testovani u eRousky) s poctem symptomaticky nemocnych v poslednich 7 dnech.
        :param: get_current_level - pokude je True, vraci funkce aktualni hondotu thresholdu a nic dalsiho neprovadi
        :return:
        '''
        current_level = self.get_threshold()
        for precaution in self.applied_precautions:
            # pro kazde opatreni v seznamu aplikovanych opatreni porovnam prislusny threshold vuci modelu a pripadne
            # opatreni aktivuji
            if precaution['trigger_threshold'] <= current_level and not precaution['is_active']:
                precaution['is_active'] = True
                precaution['chapters'] += 1 # kolikrat se pri simulaci opatreni aktivovalo
                precaution['stop_precaution_at'] = self.schedule.steps + precaution['min_duration_in_steps']
            elif precaution['is_active'] and precaution['trigger_threshold'] >= current_level \
                    and self.schedule.steps >= precaution['stop_precaution_at'] and self.schedule.steps > 504:
                # pokud je soucasny stav thresholdove hodnoty v modelu nizsi nebo roven thresholdu opatreni a vyprsi
                # minimalni trvani opatreni a ubehne ochranna doba (3 tydny, aby se opareni nevypnulo predcasne),
                # opatreni vypinam - tyka se i opatreni aktivovanych od pocatku (param !0) s vyjimkou opatreni
                # vyjmenovanych nize (ty nemaji vliv na spotrebu piva, proto je muzu nechat bezet)
                #if not (precaution['trigger_threshold'] == 0 and precaution not in (self.precaution_test, self.precaution_mask)):
                precaution['is_active'] = False
                precaution['stop_precaution_at'] = 0

    def save_contacts_optimized(self, delete_after=120):
        """
        Ulozeni kontaktu pro eRousku (app) - ukladaji se jen kontakty vybavene aplikaci nebo tokenem a to s cislem
        stepu. Vybaveni agentu je dano rozsirenim chytrych zarizeni v populaci (parameter penetration v opatreni).
        Zaznamy starsi nez delete_after se mazou.
        :arg: delete_after = pocet stepu, po ktere se drzi zaznam v databazi (vychozi hodnota 120 odpovida 5-ti dnum)
        :return:
        """
        if not self.df_smart_contacts.empty:
            # smazu expirovane zaznamy
            self.df_smart_contacts = self.df_smart_contacts.loc[(self.df_smart_contacts['step'] >= self.schedule.steps-delete_after)]
        # pridam nove kontakty
        for cell in self.df_agent_snapshot.loc[(self.df_agent_snapshot['smart_app_active']==True)].groupby('pos'):
            # pomoci loc a masky vyberu jen agenty s aplikaci, ty pak seskupim dle pozice (x,y) a projdu skupiny
            if cell[1].shape[0] > 1:
                # pokud je v lokaci vice agentu s aplikaci, ulozim je do databaze (step: seznam indexu)
                self.df_smart_contacts = self.df_smart_contacts.append({'step': self.schedule.steps, 'contacts': cell[1].index}, ignore_index=True)

    def trace_contacts_optimized(self, mask_app_tracer):
        """
        Pokud je identifikovan symptomaticky/pozitivne testovany agent, jsou dle databaze df_smart_contacts vytrasovany
        kontakty z eRousky
        :param: mask_app_tracer = nemocni nebo pozitivne testoovani agenti s chytrou aplikaci
        :return:
        """
        processed = []
        # maska mask_app_trace filtruje agenty spoustejici trasovani (nove pozitivne testovane, nove symp. nemocne)
        for agent in self.df_agent_snapshot[mask_app_tracer].itertuples():
            # noveho spousteciho agenta ulozim do seznamu pro dalsi zpracovani
            processed.append(agent.Index)
            # vyfiltruji zaznamy z databaze eRousky, ve kterych se vyskytuje spousteci agent, v db eRousky je list,
            # proto apply na iteraci rows a lambda pro kazdy list na radku
            mask_matching_entries = (self.df_smart_contacts['contacts'].apply(lambda x: agent.Index in x))
            contacts = self.df_smart_contacts.loc[mask_matching_entries, 'contacts'].values
            # seznam kontaktu je 2D, pres itertools z nej udelam 1D (flat list bez duplicit), odeberu zpracovane agenty,
            # protoze ti jedou oddelene (jsou v karantene bud kvuli testu, nebo kvuli symp. onemocneni)
            contacts = list(set(itertools.chain.from_iterable(contacts)) ^ set(processed)) # TODO: zamysli se - neni efektivnejsi misto set(porcessed pouzit self.df_agent_snapshot[mask_app_tracer].to_list()?)
            for unique_id in contacts:
                if self.precaution_smart_app['smart_action_prob'] == 1 or self.precaution_smart_app['smart_action_prob'] > random.random():
                    # pokud je pravdepodobnost nasledovani smart_action rovna 1, setrim random generator
                    if 'Q' in self.precaution_smart_app['smart_action'] and \
                            self.df_agent_snapshot.at[unique_id, 'quarantine_till'] < \
                            self.schedule.steps + self.precaution_smart_app['smart_action_duration']:
                        # agent se zkarantenizuje jen v pripade, kdy v karantene jeste neni, nebo je karantena kratsi
                        # nez nastaveni smart_action_duration
                        self.agents[unique_id].quarantinize_yourself()
                    if 'QD' in self.precaution_smart_app['smart_action']:
                        # pokud je smart_action karantena na celou domacnost kontaktu, aplikuji na vsechny agenty,
                        # kteri dosud nejsou v (dostatecne dlouhe) karantene
                        xcoord = self.df_agent_snapshot.loc[unique_id, 'coord_house_xgrid']
                        ycoord = self.df_agent_snapshot.loc[unique_id, 'coord_house_ygrid']
                        mask_household = (self.df_agent_snapshot['coord_house_xgrid']==xcoord) \
                                         & (self.df_agent_snapshot['coord_house_ygrid']==ycoord) \
                                         & (self.df_agent_snapshot['quarantine_till'] < self.schedule.steps + self.precaution_smart_app['smart_action_duration'])
                        for affected_id in self.df_agent_snapshot.loc[mask_household].to_list():
                            self.agents[affected_id].quarantinize_yourself()
                    if 'T' in self.precaution_smart_app['smart_action']:
                        # pokud je smart_action testovani, agent se otestuje
                        self.agents[unique_id].test_yourself()
                    if 'M' in self.precaution_smart_app['smart_action']:
                        # pokud je smart_action ochrana dychacich cest, agent zacne nosit rousku
                        self.agents[unique_id].mask_yourself()
                    if 'MD' in self.precaution_smart_app['smart_action']:
                        # pokud je smart_action ochrana dychacich cest pro celou domacnost, zacnou nosit rousku vsichni
                        # agenti v domacnosti v odpovidajicim veku
                        xcoord = self.df_agent_snapshot.loc[unique_id, 'coord_house_xgrid']
                        ycoord = self.df_agent_snapshot.loc[unique_id, 'coord_house_ygrid']
                        mask_household = (self.df_agent_snapshot['coord_house_xgrid']==xcoord) \
                                         & (self.df_agent_snapshot['coord_house_ygrid']==ycoord)
                        for affected_id in self.df_agent_snapshot.loc[mask_household].to_list():
                            self.agents[affected_id].mask_yourself()


    def save_infected_agent(self, agent, vector_id, ir=0, place=None, threshold=0):
        """
        Ulozeni infikovanych agentu do samostatneho dataframe (pro kontrolu spravnosti behu simulace a dalsi analyzu -
        napr. kde nejcasteji dochazi k nakazeni, vypocet cisla R apod.)
        :param agent: cil nakazy
        :param vector_id: zdroj nakazy (vironosic)
        :param ir: infekcni rate
        :param place: nazev lokace nakazy
        :return:
        """
        self.df_infected_agents = self.df_infected_agents.append({
            'victim_id': agent.unique_id,
            'victim_age': agent.age,

            'vector_age': self.df_agent_snapshot.at[int(vector_id), 'age'] if not self.df_agent_snapshot.empty and not np.isnan(vector_id) else np.nan,
            'pos': agent.pos,
            'place': agent.current_place if not place else place,
            'infected_in_step': agent.infected_in_step,
            'vector_id': vector_id,
            'vector_base_entry_ir': ir,
            'vector_final_output_ir': self.base_P * ir,
            'vector_ir_random_threshold': threshold
        }, ignore_index=True)
        if not self.df_agent_snapshot.empty:
            self.df_agent_snapshot.loc[agent.unique_id, 'infected_by'].append(vector_id) #victim.infected_by
            self.df_agent_snapshot.loc[agent.unique_id, 'infected_at_place'].append(agent.current_place if not place else place) #victim.infected_at_place
            self.df_agent_snapshot.loc[agent.unique_id, 'a_infected_by_ir'] = self.base_P * ir

    def infect_heal_or_die(self):
        step = self.schedule.steps
        # vyfiltruji uzdravene agenty a zmenim jim stav na uzdraveny a imunni
        mask_healed_agents = (self.df_agent_snapshot['regular_illness_till'] == step-1) & \
                             (self.df_agent_snapshot['sickness_result'] != 'exitus')
        for agent in self.df_agent_snapshot[mask_healed_agents].itertuples():
            self.agents[int(agent.unique_id)].heal_yourself()

        # vyfiltruji agenty s koncici imunitou a nastavim je zpatky na suspicious
        mask_healed_agents = (self.df_agent_snapshot['immune_till'] == step-1)
        for agent in self.df_agent_snapshot[mask_healed_agents].itertuples():
            self.agents[int(agent.unique_id)].suspiciousize_yourself()

        # vyfiltruji agenty s koncici karantenou a pustim je z "domaciho vezeni"
        mask_freed_agents = (self.df_agent_snapshot['quarantine_till'] == step-1)
        for agent in self.df_agent_snapshot[mask_freed_agents].itertuples():
            self.agents[int(agent.unique_id)].dequarantinize_yourself()

        if self.precaution_test['is_active']:
            # pokud je aktivni opatreni testovani, vyfiltruji agenty, kteri maji byt otestovani - nachazi se
            # na testovacim miste a dosahli frekvence testovani
            test_type_index = 1 if 'pcr' in self.precaution_test['name'] else 0
            age_categ = (int(self.precaution_test['applicable_age_categ'].split('-')[0]), int(self.precaution_test['applicable_age_categ'].split('-')[1]))
            mask_to_be_tested_agents = (self.df_agent_snapshot['age'].between(age_categ[0], age_categ[1])) & \
                                       (self.df_agent_snapshot['positive_test_at_step'] == 0) & \
                                       ((self.df_agent_snapshot['tested_at_step']+self.precaution_test['frequency_once_per_days'][test_type_index]*24 < step) | (self.df_agent_snapshot['tested_at_step'] == 0)) & \
                                       (self.df_agent_snapshot['current_place'].isin(self.precaution_test['test_places']))
            for agent in self.df_agent_snapshot[mask_to_be_tested_agents].itertuples():
                self.agents[int(agent.unique_id)].test_yourself()

        # vyfiltruji agenty s pozitivnim testem nebo nastupem regulerniho onemocneni a nastavim jim karantenu.
        # Pokud je aktivni opareni precaution_quarantine, pak nastavim karantenu podle nej i pro dalsi
        # agenty (homemates, workmates, schoolmates).
        mask_positively_tested_or_sick_agents = (self.df_agent_snapshot['positive_test_at_step'] == step-1) | \
                                        ((self.df_agent_snapshot['super_spreader_till'] == step-1) &
                                         (self.df_agent_snapshot['sicktype'].isin(['mild', 'severe'])))
        for agent in self.df_agent_snapshot[mask_positively_tested_or_sick_agents].itertuples():
            # kazdy nemocny symptomaticky/pozitivne testovany agent putuje do karanteny (to jde zcela mimo opatreni)
            self.agents[int(agent.unique_id)].quarantinize_yourself()
            if self.precaution_quarantine['is_active']:
                # pokud je aktivni karantena, pak do karanteny putuje sirsi skupina agentu
                for typ in self.precaution_quarantine['quarantine_type']:
                    if typ == 'W':
                        # karantena na pracovni kolektiv, ve kterem se vyskytuje nakazeny
                        mask_qmates = (self.df_agent_snapshot['coord_work_xgrid'] == agent.coord_work_xgrid) & \
                                      (self.df_agent_snapshot['coord_work_ygrid'] == agent.coord_work_ygrid) & \
                                      (self.df_agent_snapshot['work_type'] == 'firma')
                    elif typ == 'S':
                        # karantena na celou skolu
                        mask_qmates = (self.df_agent_snapshot['coord_work_xgrid'] == agent.coord_work_xgrid) & \
                                      (self.df_agent_snapshot['coord_work_ygrid'] == agent.coord_work_ygrid) & \
                                      (self.df_agent_snapshot['work_type'] == 'skola')
                    else:
                        # v jakemkoliv jinem pripade (melo by jit o 'D') uvazuji karantenu na celou domacnost
                        mask_qmates = (self.df_agent_snapshot['coord_house_xgrid'] == agent.coord_house_xgrid) & \
                                      (self.df_agent_snapshot['coord_house_ygrid'] == agent.coord_house_ygrid)
                    for mate in self.df_agent_snapshot[mask_qmates].itertuples():
                        self.agents[int(mate.unique_id)].quarantinize_yourself()

        # pokud je aktivni opatreni precaution_smart_app, pouziju masku i pro trasovani a pridam dodatecny filtr
        # pro agenty s aktivni eRouskou
        if self.precaution_smart_app['is_active'] and not self.df_smart_contacts.empty:
            mask_app_tracer = mask_positively_tested_or_sick_agents & (self.df_agent_snapshot['smart_app_active']==True)
            self.trace_contacts_optimized(mask_app_tracer)

        # vyfiltruji agenty, u kterych posledni den onemocneni konci umrtim a odeberu je z modelu
        mask_killed_agents = (self.df_agent_snapshot['sickness_result'] == 'exitus') & \
                             (self.df_agent_snapshot['regular_illness_till'] == step-1)
        for agent in self.df_agent_snapshot.loc[mask_killed_agents].itertuples():
            # agent, ktery onemocneni neprezije, je zaznamenan a odebran z gridu i casovace
            if self.df_deaths.empty:
                self.df_deaths = pd.DataFrame(pd.DataFrame(pd.Series(agent).drop(0)).T)
                self.df_deaths.columns = list(agent._fields)[1:]
            else:
                self.df_deaths.loc[self.df_deaths.shape[0]] = list(agent)[1:]
            self.grid.remove_agent(self.agents[int(agent.unique_id)])
            self.schedule.remove(self.agents[int(agent.unique_id)])
            if not self.df_agent_snapshot.empty:
                # odstranim agenta i z reportovaciho dataframe (ale v puvodním df_agents zustava pro vyber "retezce osudu" pri reinfekci jinych agentu)
                self.df_agent_snapshot.drop(index=agent.unique_id, inplace=True)

        # vyfiltruji aktualne nemocne a nakazene agenty (ty, kteri mohou prenaset nakazu)
        mask_ios_agents = (self.df_agent_snapshot['infected_in_step'] > 0) & \
                          (self.df_agent_snapshot['regular_illness_till'] >= step) & \
                          (self.df_agent_snapshot['non_infectious_till'] < step-1)
        # a pokusim se infikovat suspicious agenty
        for agent in self.df_agent_snapshot.loc[mask_ios_agents].itertuples():
            # pro kazdeho potencialniho prenasece prepocitam infect_rate (pokud je v blizkosti jiny agent)
            cellmates = [a for a in self.grid.get_cell_list_contents(agent.pos) if a.infected_in_step == 0]
            ir = self.agents[int(agent.unique_id)].calc_infect_rate() if cellmates else 0
            if ir:
                for victim in cellmates:
                    # projdu vsechny dosud nenakazene a neimunni agenty na stejne lokaci a pokusim se je nakazit
                    threshold = self.random.random()
                    if self.base_P * ir >= threshold:
                        self.a_newly_infected += 1
                        # pokud je agent infikovan, nastavim casove charakteristiky onemocneni
                        victim.calc_infect_periods()
                        # zaznamenam i od koho se nakaza sirila a kde k ni doslo
                        victim.infected_by.append(agent.unique_id)
                        victim.infected_at_place.append(agent.current_place)
                        self.save_infected_agent(victim, agent.unique_id, ir=ir, threshold=threshold)

                    else:
                        self.a_not_infected += 1

    def save_epidemic_features(self, start):
        step = self.schedule.steps
        mask_ios_agents = (self.df_agent_snapshot['infected_in_step'] > 0) & \
                          (self.df_agent_snapshot['regular_illness_till'] >= step)
        mask_ss_agents = mask_ios_agents & (self.df_agent_snapshot['non_infectious_till'] < step-1) & \
                         (step <= self.df_agent_snapshot['super_spreader_till'])
        mask_asym_agent = mask_ios_agents & (self.df_agent_snapshot['super_spreader_till'] < step-1) & \
                          (self.df_agent_snapshot['sicktype'] == 'asymptomatic')
        mask_mild_agent = mask_ios_agents & (self.df_agent_snapshot['super_spreader_till'] < step-1) & \
                          (self.df_agent_snapshot['sicktype'] == 'mild')
        mask_svr_agent = mask_ios_agents & (self.df_agent_snapshot['super_spreader_till'] < step-1) & \
                         (self.df_agent_snapshot['sicktype'] == 'severe')
        mask_quarrested_agents = (self.df_agent_snapshot['quarantine_till'] >= step)
        self.df_results = self.df_results.append({
            'step': self.schedule.steps,
            'infected_or_sick_agents': self.df_agent_snapshot[mask_ios_agents].shape[0],
            'super_spreader': self.df_agent_snapshot[mask_ss_agents].shape[0],
            'sick_asymptomatic': self.df_agent_snapshot[mask_asym_agent].shape[0],
            'sick_mild': self.df_agent_snapshot[mask_mild_agent].shape[0],
            'sick_severe': self.df_agent_snapshot[mask_svr_agent].shape[0],
            'death_agents': self.df_deaths.shape[0],
            'death_agents_avg_age': np.nan if self.df_deaths.shape[0] == 0 else np.round(self.df_deaths['age'].mean(), 2),

            'beer_consumption_sum_cepovane': self.beer['cepovane'],
            'beer_consumption_sum_lahvove': self.beer['lahvove'],

            'prec_test_is_active': self.precaution_test['is_active'],
            'prec_test_chapter': self.precaution_test['chapters'],
            'prec_test_tested_per_step_positively': self.tested_agents['positive'],
            'prec_test_tested_per_step_negatively': self.tested_agents['negative'],

            'prec_quarantine_is_active': self.precaution_quarantine['is_active'],
            'prec_quarantine_chapter': self.precaution_quarantine['chapters'],
            'prec_quarantine_type': self.precaution_quarantine['quarantine_type'] if self.precaution_quarantine['is_active'] else np.nan,
            'prec_quarantine_active_cases': self.df_agent_snapshot[mask_quarrested_agents].shape[0],

            'prec_smart_app_is_active': self.precaution_smart_app['is_active'],
            'prec_smart_app_chapter': self.precaution_smart_app['chapters'],

            'prec_lockdown_is_active': self.precaution_lockdown['is_active'],
            'prec_lockdown_is_chapter': self.precaution_lockdown['chapters'],
            'prec_lockdown_closed_locations': self.precaution_lockdown['closed_locations'] if self.precaution_lockdown['is_active'] else np.nan,

            'prec_mask_is_active': self.precaution_mask['is_active'],

            'a_new_infections': self.a_newly_infected,
            'a_plain_infection_attempts': self.a_not_infected,
            'step_duration': time.time() - start
        },
            ignore_index=True)

    def step(self):
        """
        Implementace kroku modelu
        :return:
        """
        # zacatek vypoctu casu behu jednoho kroku (pro int. porovnani vlivu opatreni, ruznych pristupu apod.)
        start = time.time()
        # vynuluji pocty testu (dulezite) a infekci pro novy step (ty jsou hlavne ukazateli zda simulace funguje
        # spravne a pro dalsi analyzu chovani)
        self.tested_agents = {'positive': 0, 'negative': 0}
        self.a_not_infected = 0
        self.a_newly_infected = 0

        if self.schedule.steps == 0:
            # uvodni nastaveni simulace v nultem kroku, slozita soukoli sveta se rozebehnou az od stepu 1...
            # vytvoreni snapshotu s agenty
            self.agents_to_dataframe()
            # nastaveni opatreni aplikovanych pro aktualni instanci
            self.set_applied_precautions()

            if self.precaution_smart_app in self.applied_precautions:
                # pokud je trasovaci aplikace soucasti simulace, distribuuji aplikace a tokeny mezi agenty
                self.distribute_smart_app()

            # step zvysim o 1, protoze 0 je vychozi a komparacni stav u mnoha vlastnosti modelu (alt. jsem si
            # jako default values mohl vybrat np.nan, -1,...), ale start od 1 nema na vysledky simulace
            # stejne stat. vyznamny vliv, tudiz to nevadi
            self.schedule.steps += 1
            # vypis aplikovanych opatreni a poctu kroku uzivateli
            print(f'\n{self.simtype} scenario started -> applied precautions:',
                  ', '.join([f"{p['name']} (tt:{p['trigger_threshold']} {'->immediately triggered' if p['trigger_threshold']==0 else 'of positive tests' if self.precaution_test in self.applied_precautions else 'of mild/severe symptoms'})" for p in self.applied_precautions]))
        else:
            # provedu krok modelu a kroky vsech agentu
            self.schedule.step()

            if self.simtype == 'covid':
                # pokud je covid soucasti simulace, prepocitam a aktivuji opatreni a v pripade dosazeni thresholdu
                # opatreni zapnu, nebo vypnu (hodnota is_active na True/False)
                self.calc_thresholds()
                # prepocitam sireni infekce (nove nakazy, prubehy nemoci, vyleceni, umrti)
                # a rozdam karanteny, lockdowny, poukazky na testy a jine darky
                self.infect_heal_or_die()
                if self.precaution_smart_app['is_active']:
                    self.save_contacts_optimized()

            if self.schedule.steps == self.max_steps:
                # pokud model dosahl konce behu, ulozim vysledky do csv pro dalsi analyzy a grafy do html pro kochani
                self.save_results()
                self.nice_vizualizer2()

            if not self.df_agent_snapshot.empty:
                # pokud uz je vytvoren snapshot, ulozim charakteristiky modelu do df_results
                self.save_epidemic_features(start)

            # NOTE: vestaveny Datacollector nepouzivam, ja nahrazen soubeznou zmenou snapshotu inicializovaneho na pocatku.
            # Vysledkem takoveho rozhoduti je markatni uspora casu pri behu simulace (nejde o rezii filtrace posledniho
            # stepu, ktery potrebuju, ale o to, ze Datacollector agentu v kazdem stepu prida k dataframe radky podle
            # poctu agentu a jen za 1. mesic tim dokaze simulacni krok zpomalit cca 10x...rocni simulace by pak trvala
            # pres 24h)
            #self.datacollector.collect(model=self)
            #self.df_agent_snapshot = self.datacollector.get_agent_vars_dataframe().groupby(level=1).max()
            #cols = list(self.agents[0].__dict__.keys())
            #...

    def save_results(self):
        """
        Ulozeni dataframe s vysledky (df_results) do slozky results
        :return:
        """
        path = os.path.join(self.data_path, 'results', '{}_{}_{}.csv'.format(
            self.simtype,
            self.precautions if type(self.precautions) == str else '-'.join(self.precautions),
            self.max_steps))
        #self.df_results['precaution_args'] = self.precautions
        self.df_results.to_csv(path, sep=';')
        path = os.path.join(self.data_path, 'results', '{}_{}_{}_illness_story.csv'.format(
            self.simtype,
            self.precautions if type(self.precautions) == str else '-'.join(self.precautions),
            self.max_steps))
        #self.df_infected_agents['precaution_args'] = self.precautions
        self.df_infected_agents.to_csv(path, sep=';')


    def nice_vizualizer(self, x_vals, y_vals):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x_vals, y=y_vals))
        path = os.path.join(self.data_path, 'results', '{}_{}_{}.html'.format(
            self.simtype,
            self.precautions if type(self.precautions) == str else '-'.join(self.precautions),
            self.max_steps))
        fig.write_html(path)

    def nice_vizualizer2(self, df_datastore=None):
        if not df_datastore:
            plots = [
                {'x': self.df_results['step'], 'y':self. df_results['super_spreader'], 'name': 'Superprenaseci'},
                {'x': self.df_results['step'], 'y': self.df_results['sick_asymptomatic'], 'name': 'Asymptomaticke prubehy'},
                {'x': self.df_results['step'], 'y': self.df_results['sick_mild'], 'name': 'Mirne a stredni prubehy'},
                {'x': self.df_results['step'], 'y': self.df_results['sick_severe'], 'name': 'Vazne prubehy'},
            ]
            if 'mask' in ','.join(self.precautions):
                plots.append({'x': self.df_results['step'], 'y': self.df_results['prec_mask_is_active'], 'name': 'Aktivni opatreni - rousky'})
            if 'quarantine' in ','.join(self.precautions):
                plots.append({'x': self.df_results['step'], 'y': self.df_results['prec_quarantine_is_active'], 'name': 'Aktivni opatreni - karantena'})
            if 'app' in ','.join(self.precautions):
                plots.append({'x': self.df_results['step'], 'y': self.df_results['prec_smart_app_is_active'], 'name': 'Aktivni opatreni - trasovaci aplikace'})
            if 'lockdown' in ','.join(self.precautions):
                plots.append({'x': self.df_results['step'], 'y': self.df_results['prec_lockdown_is_active'], 'name': 'Aktivni opatreni - lockdown'})
            elif 'sector' in ','.join(self.precautions):
                # TODO tip: umoznit koexistenci sector a lockdown s ruznymi tt (napr. sector od 1. symptomatika a lockdown od 50.) - zmena definice prepoctu thresholdu ve stepu
                plots.append({'x': self.df_results['step'], 'y': self.df_results['prec_lockdown_is_active'], 'name': f'Aktivni opatreni - sektor ({"+".join(self.precaution_lockdown["closed_locations"])})'})
            if 'test' in ','.join(self.precautions):
                plots.append({'x': self.df_results['step'], 'y': self.df_results['prec_test_is_active'], 'name': 'Aktivni opatreni - testovani'})

            fig = ps.make_subplots(rows=1, cols=2, specs=[[{"type": "scatter"}, {"type": "pie"}]],
                                   subplot_titles=("Prubeh epidemie", "Nejcastejsi mista nakazy"),
                                   column_widths=[0.7, 0.3])

            highest_val = 0
            color = 0
            for plot in plots:
                if not plot['y'].name.startswith('prec_'):
                    fig.add_trace(go.Scatter(x=plot['x'], y=plot['y'], name=plot['name']), row=1, col=1)
                    highest_val = plot['y'].max() if highest_val < plot['y'].max() else highest_val
            pr_base_y = 0
            pr_incr_y = math.ceil(highest_val/100) if highest_val > 0 else 1
            for plot in plots:
                if plot['y'].name.startswith('prec_') and plot['y'].name.endswith('_is_active'):
                    signals = (np.sign(plot['y']).diff().ne(0))
                    signals = signals[signals==True].index.tolist()
                    if plot['y'][0]==0:
                        if len(signals)%2==0:
                            signals.append(plot['x'].max())
                        signals = signals[1:]
                    elif plot['y'][0]==1 and len(signals)==1:
                        signals.append(plot['x'].max())
                    rect_xcoords = [signals[i:i + 2] for i in range(0, len(signals), 2)]
                    xcoords = []
                    ycoords = []
                    for x in rect_xcoords:
                        if len(x)==1:
                            x[0] -= 1
                            x.append([self.max_steps])
                        if xcoords:
                            xcoords.extend([None])
                            ycoords.extend([None])
                        xcoords.extend([x[0], x[1], x[1], x[0], x[0]])
                        #print([x[0], x[1], x[1], x[0], x[0]])
                        #print([-pr_base_y, -pr_base_y, -pr_base_y-pr_incr_y, -pr_base_y-pr_incr_y, -pr_base_y])
                        ycoords.extend([-pr_base_y, -pr_base_y, -pr_base_y-pr_incr_y, -pr_base_y-pr_incr_y, -pr_base_y])
                    fig.add_trace(go.Scatter(mode='lines', x=xcoords, y=ycoords, line_width=0, fill="toself",
                                             fillcolor=px.colors.qualitative.Alphabet[color],
                                             opacity=1, name=plot['name'], hovertext=plot['name']), row=1, col=1)
                    color += 1
                    pr_base_y += pr_incr_y

            if self.df_infected_agents.empty:
                self.df_infected_agents = pd.DataFrame(columns = ['place', 'victim_age'], data=None)
            self.df_infected_agents.loc[
                ((self.df_infected_agents['place']=='W') & (self.df_infected_agents['victim_age']<18)), 'place'] = 'S'
            dangerous_places = self.df_infected_agents.groupby(['place']).size().reset_index(name='counts')
            dangerous_places.replace(
                {'D': 'Doma', 'W': 'Pracoviste', 'S': 'Skola', 'P': 'Priroda', 'N': 'Nakupni zony', 'R': 'Restaurace',
                 'Ext': 'Externi', 'H': 'Nemocnice'}, inplace=True)
            fig.add_trace(
                go.Pie(labels=dangerous_places['place'].values.tolist(),
                       values=dangerous_places['counts'].values.tolist(), textinfo='label+percent', showlegend=False),
                row=1, col=2)

            fig.add_annotation(text=f"Simulace ({round(self.max_steps/24,1)} dnu): {self.simtype} - {self.precautions}",
                               xref="paper", yref="paper",
                               font=dict(family="nasalization, verdana, sans serif, arial", size=18, color="crimson"),
                               x=0, y=1.2, showarrow=False)
            sim = round(self.df_results['beer_consumption_sum_lahvove'].max(), 2)
            per = round(sim/(len(self.agents)+self.df_deaths.shape[0]), 2)
            fig.add_annotation(text=f"Spotreba (za simulaci|na osobu [l]) LAHVOVE: {sim} | {per}",
                               xref="paper", yref="paper",
                               x=0, y=1.14, showarrow=False)
            sim = round(self.df_results['beer_consumption_sum_cepovane'].max(), 2)
            per = round(sim/(len(self.agents)+self.df_deaths.shape[0]), 2)
            fig.add_annotation(text=f"Spotreba (za simulaci|na osobu [l]) CEPOVANE: {sim} | {per}",
                               xref="paper", yref="paper",
                               x=0, y=1.1, showarrow=False)
            fig.update_layout(hovermode='x', template='plotly_dark',
                              legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="right", x=1)
                              #,xaxis=dict(rangeslider=dict(visible=True))
                              )

            #fig.update_layout(hovermode='x', template='plotly_white')
            #fig.show()
            path = os.path.join(self.data_path, 'results', '{}_{}_{}.html'.format(
                self.simtype,
                self.precautions if type(self.precautions) == str else '-'.join(self.precautions),
                self.max_steps))
            fig.write_html(path)
        else:
            pass
        #return fig
