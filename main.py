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
    parser.add_argument("-n", "--steps", help="pocet kroku - hodnota je pouzita pro vsechny simulace; pri neuvedeni argumentu "
                                              "je vychozi hodnota 720 (1 krok = 1 hodina, 6-ti mesicni simulace = 4320 kroku)")
    parser.add_argument("-f", "--configle", help="cesta k csv souboru s konfiguraci simulace "
                                                 "(simtyp;sekvence resp. simtyp;sekvence1,sekvence2)")
    parser.add_argument("-s", "--simtype", help="typ simulace - covid, no covid - pokud neni uvedeno, modeluje se "
                                                "simtype = covid; pokud je uveden --configle, je argument simtype ignorovan")
    parser.add_argument("-p", "--precautions", help="sekvence opatreni - jednotliva opatreni v sekvenci jsou oddelena carkou, "
                                                    "jendotlive sekvence strednikem; pokud je uveden --configle, je argument "
                                                    "precautions ignorovan")
    parser.add_argument("-e", "--seed", help="hodnota seedu pro generatory pseudonahodnych cisel")
    args = parser.parse_args()
    params_library = []
    param_story = {'variable_params': {}, 'fixed_params': {}}

    if args.generator:
        return ['generator', int(args.seed)] if args.seed else ['generator']
    else:
        if args.steps:
            param_story['fixed_params']['max_steps'] = int(args.steps)
        else:
            param_story['fixed_params']['max_steps'] = 720
        if args.seed:
            param_story['fixed_params']['random_seed'] = int(args.seed)
        if args.configle:
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

    params_library = get_cmd_args()
    print(params_library)
    if 'generator' in params_library:
        if len(params_library) > 1:
            generator.run(seed=params_library[1])
        else:
            generator.run()
    else:
        simulator.run(params_library)

    print('All the hard work done!')