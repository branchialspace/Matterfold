# Mayer and Minimal Basis Iterative Stockholder (MBIS) bonding site analysis in ORCA

import os
import subprocess
import re
from ase import Atoms
from ase.data import atomic_numbers, chemical_symbols

def electron_bonding_sites(ligand, charge=0, mult=1, method='B3LYP', basis_set='def2-SVP'):
    """
    Identify potential cations, anions, and atoms for covalent bonding in a ligand.

    Parameters:
    - ligand: ASE Atoms object representing the ligand molecule.
    - charge: Overall charge of the ligand.
    - mult: Spin multiplicity of the ligand.
    - method: Quantum chemistry method to use (e.g., 'B3LYP').
    - basis_set: Basis set to use (e.g., 'def2-SVP').

    Returns:
    - bonding_sites: Dictionary containing information about each atom's bonding role.
    """
    # Define the ORCA executable path
    orca_path = '/root/orca_6_0_0/orca'

    # Define filenames
    input_filename = 'orca_input.inp'
    output_filename = 'orca.out'

    # Write the ORCA input file
    write_orca_input(ligand, input_filename, charge, mult, method, basis_set)

    # Run ORCA
    try:
        with open(output_filename, 'w') as f_out:
            subprocess.run([orca_path, input_filename], stdout=f_out, stderr=subprocess.STDOUT, check=True)
        print("ORCA calculation completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error during ORCA calculation: {e}")
        return {}

    # Parse the energy
    energy = parse_energy(output_filename)
    print(f"Calculation completed. Energy: {energy}")

    # Parse the output file
    mayer_data = parse_mayer_data(output_filename)
    mbis_data = parse_mbis_data(output_filename)
    bonding_sites = find_potential_bonding_sites(mayer_data, mbis_data)

    return bonding_sites

def write_orca_input(ligand, filename, charge, mult, method, basis_set):
    with open(filename, 'w') as f:
        # Write method and basis set
        f.write(f"! {method} {basis_set} MBIS\n")
        f.write("%output\n")
        f.write("    Print[P_MBIS] 1\n")
        f.write("    Print[P_Mayer] 1\n")
        f.write("end\n\n")
        f.write("%method\n")
        f.write("    MAYER_BONDORDERTHRESH 0.05\n")
        f.write("end\n\n")
        # Write charge and multiplicity
        f.write(f"* xyz {charge} {mult}\n")
        # Write atomic coordinates
        for atom in ligand:
            symbol = atom.symbol
            x, y, z = atom.position
            f.write(f"  {symbol} {x:.6f} {y:.6f} {z:.6f}\n")
        f.write("*\n")

def parse_energy(filename):
    with open(filename, 'r') as f:
        lines = f.readlines()

    energy = None
    for line in lines:
        if 'FINAL SINGLE POINT ENERGY' in line:
            parts = line.strip().split()
            if len(parts) >= 5:
                energy = float(parts[4])
                break
    return energy

def parse_mayer_data(filename):
    mayer_data = {'bond_orders': {}}
    with open(filename, 'r') as f:
        lines = f.readlines()

    bond_order_section = False
    bond_order_lines = []
    for i, line in enumerate(lines):
        if 'MAYER POPULATION ANALYSIS' in line:
            bond_order_section = True
            continue
        if bond_order_section and 'Mayer bond orders larger than' in line:
            # Start reading bond orders
            for j in range(i+1, len(lines)):
                line_content = lines[j].strip()
                if line_content == '':
                    continue
                if '****' in line_content or 'Population analysis' in line_content:
                    # Reached the end of bond orders
                    break
                bond_order_lines.append(line_content)
            break

    # Combine bond order lines into a single string for regex parsing
    bond_order_text = ' '.join(bond_order_lines)

    # Now parse the bond order text
    bond_order_pattern = r'B\(\s*(\d+)-\w+\s*,\s*(\d+)-\w+\s*\)\s*:\s*([\d\.]+)'
    matches = re.findall(bond_order_pattern, bond_order_text)
    for match in matches:
        atom1 = int(match[0])
        atom2 = int(match[1])
        order = float(match[2])
        mayer_data['bond_orders'][(atom1, atom2)] = order

    return mayer_data

def parse_mbis_data(filename):
    mbis_data = {}
    with open(filename, 'r') as f:
        lines = f.readlines()

    mbis_section = False
    for i, line in enumerate(lines):
        if 'MBIS ANALYSIS' in line:
            mbis_section = True
            continue
        if mbis_section and 'ATOM     CHARGE    POPULATION     SPIN' in line:
            # Now, read the data
            for j in range(i+1, len(lines)):
                line_content = lines[j].strip()
                if line_content == '' or 'MBIS VALENCE-SHELL DATA' in line_content or 'Total charge' in line_content:
                    break
                parts = line_content.split()
                if len(parts) >= 4 and parts[0].isdigit():
                    atom_index = int(parts[0])
                    element = parts[1]
                    charge = float(parts[2])
                    mbis_data[atom_index] = {'element': element, 'charge': charge}
            break

    return mbis_data

def get_valence_electrons(element):
    atomic_number = [a.number for a in Atoms(element)][0]
    noble_gases = ['He', 'Ne', 'Ar', 'Kr', 'Xe', 'Rn']
    noble_gas_atomic_numbers = [atomic_numbers[s] for s in noble_gases]
    core_electrons = max([n for n in noble_gas_atomic_numbers if n < atomic_number] + [0])
    return atomic_number - core_electrons

def find_potential_bonding_sites(mayer_data, mbis_data):
    """
    Identify potential bonding sites in the molecule.

    Parameters:
    - mayer_data: Dictionary containing Mayer bond orders.
    - mbis_data: Dictionary containing MBIS charges.

    Returns:
    - bonding_sites: Dictionary with bonding information for each atom.
    """
    bonding_sites = {}

    for atom_index, mbis_info in mbis_data.items():
        element = mbis_info['element']
        mbis_charge = mbis_info['charge']

        # Get valence electrons
        valence_electrons = get_valence_electrons(element)

        # Available electrons: valence electrons minus MBIS charge
        available_electrons = valence_electrons - mbis_charge

        # Get bonding electrons from Mayer bond orders
        bonding_electrons = sum(order for (a1, a2), order in mayer_data['bond_orders'].items() if atom_index in (a1, a2))

        # Calculate free electrons (available for external bonding)
        free_electrons = available_electrons - bonding_electrons

        # Initialize bonding site info
        bonding_sites[atom_index] = {
            'element': element,
            'available_electrons': available_electrons,
            'mbis_charge': mbis_charge,
            'bonding_electrons': bonding_electrons,
            'free_electrons': free_electrons
        }

    return bonding_sites
