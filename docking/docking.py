import sys
import subprocess
import os
import argparse
from time import time
import numpy as np
import pybel
import shutil
import csv

script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, '..'))

if __name__ == '__main__':
    from utils import soft_mkdir

RECEPTOR_PATH = os.path.join(script_dir, 'data_docking/drd3.pdbqt')
CONF_PATH = os.path.join(script_dir, 'data_docking/conf.txt')


def set_path(computer):
    if computer == 'rup':
        PYTHONSH = '/home/mcb/users/jboitr/local/mgltools_x86_64Linux2_1.5.6/bin/pythonsh'
        VINA = '/home/mcb/users/jboitr/local/autodock_vina_1_1_2_linux_x86/bin/vina'
    elif computer == 'cedar':
        PYTHONSH = '/home/jboitr/projects/def-jeromew/docking_setup/mgltools_x86_64Linux2_1.5.6/bin/pythonsh'
        VINA = '/home/jboitr/projects/def-jeromew/docking_setup/autodock_vina_1_1_2_linux_x86/bin/vina'
    elif computer == 'pasteur':
        PYTHONSH = '/c7/home/vmallet/install/mgltools_x86_64Linux2_1.5.7/bin/pythonsh'
        VINA = '/c7/home/vmallet/install/autodock_vina_1_1_2_linux_x86/bin/vina'
    elif computer == 'mac':
        PYTHONSH = '/Users/vincent/bins/mgltools_1.5.7_MacOS-X/bin/pythonsh'
        VINA = '/Users/vincent/bins/vina/bin/vina'
    else:
        print('Error: "server" argument never used before. Set paths of vina/mgltools installs for this server.')
    return PYTHONSH, VINA


def prepare_receptor():
    # just run pythonsh prepare_receptor4.py -r drd3.pdb -o drd3.pdbqt -A hydrogens
    subprocess.run(f"{PYTHONSH} prepare_receptor4.py -r drd3.pdb -o {RECEPTOR_PATH} -A hydrogens".split())


def dock(smile, unique_id, pythonsh=None, vina=None, parallel=True, exhaustiveness=16):
    """"""

    if pythonsh is None or vina is None:
        global PYTHONSH
        pythonsh = PYTHONSH
        global VINA
        vina = VINA

    soft_mkdir('tmp')
    tmp_path = f'tmp/{unique_id}'
    soft_mkdir(tmp_path)

    try:
        pass
        # PROCESS MOLECULE
        mol = pybel.readstring("smi", smile)
        mol.addh()
        mol.make3D()
        dump_mol2_path = os.path.join(tmp_path, 'ligand.mol2')
        dump_pdbqt_path = os.path.join(tmp_path, 'ligand.pdbqt')
        mol.write('mol2', dump_mol2_path, overwrite=True)
        subprocess.run(f'{pythonsh} prepare_ligand4.py -l {dump_mol2_path} -o {dump_pdbqt_path} -A hydrogens'.split())

        start = time()
        # DOCK
        cmd = f'{vina} --receptor {RECEPTOR_PATH} --ligand {dump_pdbqt_path}' \
            f' --config {CONF_PATH} --exhaustiveness {exhaustiveness} --log log.txt'
        if parallel:
            # print(cmd)
            subprocess.run(cmd.split())
        else:
            cmd += ' --cpu 1'
            subprocess.run(cmd.split())
        delta_t = time() - start
        print("Docking time :", delta_t)

        with open(os.path.join(tmp_path, 'ligand_out.pdbqt'), 'r') as f:
            lines = f.readlines()
            slines = [l for l in lines if l.startswith('REMARK VINA RESULT')]
            values = [l.split() for l in slines]
            # In each split string, item with index 3 should be the kcal/mol energy.
            score = np.mean([float(v[3]) for v in values])
    except:
        score = 0
    try:
        pass
        shutil.rmtree(tmp_path)
    except FileNotFoundError:
        pass
    return score


def one_slurm(list_data, id, path, parallel=True, exhaustiveness=16):
    """

    :param list_data: (list_smiles, list_active, list_px50)
    :param id:
    :param path:
    :param parallel:
    :param exhaustiveness:
    :return:
    """
    list_smiles, list_active, list_px50 = list_data
    with open(path, 'w', newline='') as csvfile:
        csv.writer(csvfile).writerow(['smile', 'active', 'affinity', 'score'])

    for i, smile in enumerate(list_smiles):
        score_smile = dock(smile, unique_id=id, parallel=parallel, exhaustiveness=exhaustiveness)
        # score_smile = 0
        with open(path, 'a', newline='') as csvfile:
            csv.writer(csvfile).writerow([smile,
                                          list_active[i],
                                          list_px50[i],
                                          score_smile])


def load_csv(path='to_dock_shuffled.csv'):
    import pandas as pd

    df = pd.read_csv(path)
    smiles = df['SMILES'].values
    actives = df['Activity_Flag'].values
    px50 = df['pXC50'].values
    return smiles, actives, px50


if __name__ == '__main__':
    pass

    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--server", default='mac', help="Server to run the docking on, for path and configs.")
    parser.add_argument("-e", "--ex", default=16, help="exhaustiveness parameter for vina")
    args, _ = parser.parse_known_args()

    PYTHONSH, VINA = set_path(args.server)

    # ==========SLURM=============
    proc_id, num_procs = int(sys.argv[1]), int(sys.argv[2])

    dirname = os.path.join(script_dir, 'docking_results')
    if not os.path.isdir(dirname):
        os.mkdir(dirname)

    list_smiles, list_active, list_px50 = load_csv(os.path.join(script_dir, 'to_dock_shuffled.csv'))
    N = len(list_smiles)

    chunk_size = N // num_procs
    chunk_min, chunk_max = proc_id * chunk_size, (proc_id + 1) * chunk_size
    list_data = list_smiles[chunk_min:chunk_max], list_active[chunk_min:chunk_max], list_px50[chunk_min:chunk_max]
    #
    one_slurm(list_data,
              id=proc_id,
              path=os.path.join(dirname, f"{proc_id}.csv"),
              parallel=False,
              exhaustiveness=args.ex)

    # one_slurm(['toto','tata','titi'], 1, 'zztest')
    # dock('CC1C2CCC(C2)C1CN(CCO)C(=O)c1ccc(Cl)cc1', unique_id=2, exhaustiveness=args.ex)