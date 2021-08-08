
from mesa import Agent
import random


class BeerAgent(Agent):
    """
    BeerAgent class:
    -> trida agentu popijejicich pivo a nebo taky vubec ne (treba pod 18 jen limcu)
    """
    def __init__(self, agent, model, route_plan, random_seed=42):
        """
        Konstruktor prebira informace o agentech z csv a pouziva jednotny seed pro vsechna random cisla v instanci(ch)
        :param agent: informace o agentovi nactena z csv (vek, pohlavi, spolecna domacnost apod.)
        :param model: model, ke kteremu je agent prirazen
        :param route_plan: pohybovy retezec agenta nacteny y csv
        :param random_seed: seed pro random hodnoty
        """

        super().__init__(agent.Index, model)
        self.random.seed(random_seed) # nastaveni seedu pro generator (pro reproducibilitu experimentu)
        self.seed = random_seed
        random.seed(random_seed)

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
        self.beer_fundamentalist = agent.prechod_na_lahvove_podil # pravdepodobnost nahrady cepovaneho lahvovym pri nemoznosti jit do restaurace

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
        # pivo piji jen agenti zletili a s nastavenou spotrebou alespon jednoho z druhu piv
        if self.age >= self.model.beer_age_limit and (self.tydenni_spotreba_cepovane > 0 or self.tydenni_spotreba_lahvove > 0):
            # prepocitam spotrebu cepovaneho piva na nasledujici tyden podle poctu navstev restauraci
            happy_hours = self.route_plan.to_list().count('R')
            if self.tydenni_spotreba_cepovane > 0:
                if happy_hours == 0:
                    x = 1
                assert happy_hours > 0, \
                    'Chyba dat Generatoru: Agent s nenulovou spotrebou cepovaneho piva nema v route_plan lokaci R!'
            # mimo pivni spotreby ukladam i pocet useku pro piti na index 1, coz je ale pro R nepodstatne
            self.beers_per_hour['restaurace'] = [self.tydenni_spotreba_cepovane / happy_hours, happy_hours]
            if not self.model.df_agent_snapshot.empty:
                self.model.df_agent_snapshot.at[self.unique_id, 'beers_per_hour']['restaurace'] = [self.tydenni_spotreba_cepovane / happy_hours, happy_hours]
            # a to same pro lahvove pivo popijene doma (pro potreby modelu nerozhoduje denni doba konzumace)
            happy_hours = self.route_plan.to_list().count('D')
            if self.tydenni_spotreba_lahvove > 0:
                assert happy_hours > 0, \
                    '!!!CRITICAL DATA ERROR!!!\nChyba dat Generatoru: Agent s nenulovou spotrebou lahvoveho piva ' \
                    'nema v route_plan lokaci D!'
            if happy_hours:
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
            if place_to_move == 'R':
                # agent mel puvodne namireno do R, zmenu musim poznacit pro pripadne nahrazeni pulitru lahvacem,
                # agenty v mild a severe sympto fazi pak resim v ramci beer_yourself
                unscheduled_home = True
            place_to_move = 'D'
        elif self.model.simtype == 'covid' and place_to_move in ('R', 'N'):
            # pokud se otevrene siri epidemie, budou se agenti snazit vyhnout riziku nakazy ve zbytnych lokacich - snaha
            # bude tim vetsi, cim vice nemocnych nebo pozitivne testovanych agentu bude model obsahovat a cim starsi
            # je agent (agent vi, ze s poctem nakazenych roste pravdepodobnost infikace a s vekem i riziko vaznejsiho
            # prubehu a radeji tedy zustane doma)
            p = self.model.get_threshold() * self.model.agent_age_categs.index(self.age_categ) / (1 * self.model.df_agent_snapshot.shape[0])
            rand = random.random()
            if 0 < rand < p:
                if place_to_move == 'R':
                    unscheduled_home = True
                    # agent se rozhodl vzhledem ke stavu epidemie navstevu restaurace odlozit a radeji zustat doma
                    # - zvednu modelovy citac neuskutecnenych navstev restaurace
                    self.model.a_postponed_r_visit += 1
                place_to_move = 'D'

        elif self.model.precaution_lockdown['is_active']:
            # pokud agent neni nemocny ani v karantene, pak kontroluji sektorova omezeni nebo lockdown
            if 'R' in self.model.precaution_lockdown['closed_locations'] and place_to_move == 'R':
                # sektorove uzavreni restauraci - agenti vyberou nahradni lokaci (domu, do prirody nebo na nakup)
                random_place = self.random.choice(['D', 'P', 'N'])
                unscheduled_home = True
                place_to_move = random_place
            if 'W' in self.model.precaution_lockdown['closed_locations'] and place_to_move == 'W':
                # sektorove uzavreni firem - agenti vyberou nahradni lokaci (domu, do prirody nebo na nakup)
                random_place = self.random.choice(['D', 'P', 'N'])
                place_to_move = random_place
            if 'S' in self.model.precaution_lockdown['closed_locations'] and place_to_move == 'S':
                # sektorove uzavreni skol - agenti vyberou nahradni lokaci (s nejvetsi pravdepodonosti domu, obcas i do prirody nebo na nakup)
                random_place = self.random.choice(['D', 'P', 'D', 'N', 'D'])
                place_to_move = random_place

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
                # agent jde do restaurace podle sveho planu - zvednu modelovy citac uspesne realizace navstevy
                self.model.a_realized_r_visit +=1
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
                self.model.df_agent_snapshot.at[self.unique_id, 'pos'] = tuple(map(lambda q: int(q), destination))
        if place_to_move == 'D' and unscheduled_home:
            # pokud je agent doma neplanovane (karantena, lockdown,...) misto R, muze nahradit cepovane lahvovym (pravdepodobnost vychazi z Generatoru)
            # TODO: aplikovat nahradni pijaky podle klice pivo z Generatoru
            if random.random() <= self.beer_fundamentalist:
                # pokud se agent rozhodne pit pivo, vzpije v dane situaci stejne mnozstvi jako v restauraci
                self.beer_yourself(where='R')
                #print('bottle is better than nothing')
        else:
            self.beer_yourself(where=place_to_move)
