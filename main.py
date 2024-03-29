# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import pandas as pd
import argparse
import generator
import simulator


def get_cmd_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-g", "--generator", help="pokud je zadan argument generator, spousti se generovani nove populace, "
                                                  "bez simulace - POZOR! Nova populace vzdy prepise puvodni!",
                        action='store_true')
    parser.add_argument('--pop', help='velikost populace generatoru (--pop lze kombinovat pouze s -g/--generator)')
    parser.add_argument("-n", "--steps", help="pocet kroku - hodnota je pouzita pro vsechny simulace; pri neuvedeni argumentu "
                                              "je vychozi hodnota 720 (1 krok = 1 hodina, 6-ti mesicni simulace = 4320 kroku)")
    #parser.add_argument("-f", "--configle", help="TODO: cesta k csv souboru s konfiguraci simulace "
    #                                             "(simtyp;sekvence resp. simtyp;sekvence1,sekvence2)")
    parser.add_argument("-s", "--simtype", help="typ simulace - covid, no_covid - pokud neni uvedeno, modeluje se "
                                                "simtype = covid; pokud je uveden --configle, je argument simtype ignorovan")
    parser.add_argument("-p", "--precautions", help="sekvence opatreni - jednotliva opatreni v sekvenci jsou oddelena carkou, "
                                                    "jendotlive sekvence strednikem; pokud je uveden --configle, je argument "
                                                    "precautions ignorovan")
    parser.add_argument("-e", "--seed", help="hodnota seedu pro generatory pseudonahodnych cisel")
    parser.add_argument("-a", "--patient", help="cislo pacienta 0 - pokud neni zadano, je vybran nahodny pacient 0")
    parser.add_argument("-i", '--iterations', help="pocet iteraci pro spusteni scenaru v simulatoru - vysledek je zprumerovan")
    args = parser.parse_args()
    params_library = []
    param_story = {'variable_params': {}, 'fixed_params': {}}

    if args.generator:
        dct = {'generator': True}
        if args.pop:
            dct['soc_size'] = int(args.pop)
        if args.seed:
            dct['seed'] = int(args.seed)
        return dct
    else:
        if args.steps:
            param_story['fixed_params']['max_steps'] = int(args.steps)
        else:
            param_story['fixed_params']['max_steps'] = 720
        if args.seed:
            param_story['fixed_params']['random_seed'] = int(args.seed)
        if args.patient:
            param_story['fixed_params']['random_patient_0'] = int(args.patient)
        if 1 == 0 and args.configle:
            # TODO zapracovat na impelementaci konfiguracniho souboru, do te doby never True
            print(f"config file {args.configle}")
            df_ini = pd.read_csv(args.configle, sep=';')
            mask_base = (df_ini.columns[0]=='no_covid') | ((df_ini.columns[0]=='covid') & (df_ini.columns[1].isna))
            simtype = df_ini.iloc[mask_base, 0].unique().to_list()
            if simtype:
                param_story['variable_params']['simtype'] = simtype
                params_library.append(param_story)
            precautions = df_ini.iloc[~mask_base, 0].unique().to_list()
            if precautions:
                param_story['variable_params']['precautions'] = precautions
                param_story['fixed_params']['simtype'] = 'covid'
                params_library.append(param_story)
            print('params: ', params_library)
        else:
            if args.precautions:
                param_story['variable_params']['precautions'] = args.precautions.split(';')
                param_story['fixed_params']['simtype'] = 'covid'
                params_library.append(param_story)
            elif args.simtype:
                param_story['variable_params']['simtype'] = args.simtype.split(';')
                params_library.append(param_story)
        if not params_library:
            param_story['variable_params']['simtype'] = ['covid', 'no_covid']
            params_library.append(param_story)

        return params_library


if __name__ == '__main__':

    # TODO tip pro porovnani scenaru: zmena frekvence testu - antigen 3,7, PCR 3,7;
    # TODO tip pro implementaci: long covid - zdravotni nasledky po prodelani onemocneni,
    #                            prubezna externi infikace
    #                            pooling 1:10 u PCR testu

    params_library = get_cmd_args()
    print(params_library)
    if 'generator' in params_library:
        generator.run(params_library)
    else:
        if 'iterations' in params_library:
            for i in range(params_library['iterations']):
                simulator.run(params_library, i)
        else:
            simulator.run(params_library)

    print('All the hard work done!')