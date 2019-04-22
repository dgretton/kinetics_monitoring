#!python3

import sys, os, time, logging, types, sqlite3
import pdb
from easygui import msgbox, ccbox

this_file_dir = os.path.dirname(__file__)
pyham_methods_dir = os.path.abspath(os.path.join(this_file_dir, '..'))
reader_results_dir = os.path.abspath(os.path.join(pyham_methods_dir, '..', '..', 'plate_reader_results'))

basic_pace_mod_path = os.path.join(pyham_methods_dir, 'basic_pace')
if basic_pace_mod_path not in sys.path:
    sys.path.append(basic_pace_mod_path)

from basic_pace_181024 import ( oemerr,
    LayoutManager, ResourceType, Plate24, Plate96, Tip96,
    HamiltonInterface, ClarioStar, LBPumps, Shaker, PlateData,
    initialize, hepa_on,
    tip_pick_up_96, tip_eject_96, aspirate_96, dispense_96,
    resource_list_with_prefix, read_plate, add_robot_level_log, add_stderr_logging,
    run_async, yield_in_chunks, log_banner)

def ensure_meas_table_exists(db_conn):
    '''
    Definitions of the fields in this table:
    Exactly one of the following should have a value:
        lagoon_number - the number of the lagoon, uniquely identifying the experiment, zero-indexed
        turb_number - the number of a turbidostat, uniquely identifying the culture contained
    filename - absolute path to the file in which this data is housed
    plate_id - ID field given when measurement was requested, should match ID in data file
    timestamp - time at which the measurement was taken
    well - the location in the plate reader plate where this sample was read, e.g. 'B2'
    measurement_delay_time - the time, in minutes, after the sample was pipetted that the
                            measurement was taken. For migration, we consider this to be 0
                            minutes in the absense of pipetting time values
    reading - the raw measured value from the plate reader
    data_type - 'lum' 'abs' or the spectra values for the fluorescence measurement
    '''
    c = db_conn.cursor()
    c.execute('''CREATE TABLE if not exists measurements
                (filename, plate_id, timestamp, well, reading, data_type)''')
    db_conn.commit()

def db_add_plate_data(db_name, plate_data, data_type, plate):
    db_conn = sqlite3.connect(db_name)
    ensure_meas_table_exists(db_conn)
    c = db_conn.cursor()
    for read_well in range(96):
        filename = plate_data.path
        plate_id = plate_data.header.plate_ids[0]
        timestamp = plate_data.header.time
        well = plate.position_id(read_well)
        measurement_delay_time = 0.0
        reading = plate_data.value_at(*plate.well_coords(read_well))

        data = (filename, plate_id, timestamp, well, reading, data_type)
        c.execute("INSERT INTO measurements VALUES (?,?,?,?,?,?)", data)
    db_conn.commit()
    db_conn.close()

def create_if_needed(dirname):
    if not os.path.exists(dirname):
        os.mkdir(dirname)
    return dirname

if __name__ == '__main__':
    users_dir = create_if_needed(os.path.join(this_file_dir, 'Users'))
    local_log_dir = create_if_needed(os.path.join(this_file_dir, 'log'))
    with open(os.path.expanduser('~\\.roboid')) as f:
        roboid = f.read()
    assert roboid in ('00001', '00002')
    main_logfile = os.path.join(local_log_dir, roboid + '_main.log')
    logging.basicConfig(filename=main_logfile, level=logging.DEBUG, format='[%(asctime)s] %(name)s %(levelname)s %(message)s')
    add_robot_level_log()
    add_stderr_logging()
    def line_property(ln):
        try:
            return ln.split(':')[1].strip()
        except IndexError:
            print('you need to have colons in your config lines')
            exit()

    if len(sys.argv) < 2:
        msg = 'Must supply user name as first argument. See https://paper.dropbox.com/doc/Kinetics-Monitoring-How-To--AbdTX86V2M08Kl~W1zlcNGGZAg-IeJqIgS2n5Xwbaj5hbWvz#:uid=905621552118760454976077&h2=Run-the-method for help.'
        print(msg)
        msgbox(msg)
        exit()
    user = sys.argv[1]
    new_user = not any((user.upper() == u.upper() for u in os.listdir(users_dir)))
    if new_user and not ccbox('No known user "' + user + '." Create new user?'):
        exit()

    paramsfile = 'params.cfg'
    for arg in sys.argv[2:]:
        if arg[0] == '-':
            continue
        if '.cfg' in arg:
            paramsfile = arg
            break

    with open(paramsfile) as f:
        paramlist = list(f.readlines())
    def propty(name):
        for line in paramlist:
            if name.lower() in line.lower():
                return line_property(line)
        else:
            print('property "' + name + '" not found')
            raise ValueError()
    num_plates = int(propty('plates'))
    protocols = [s.strip() for s in propty('protocols').split(',')]
    exp_name = propty('experiment name')
    this_user_dir = create_if_needed(os.path.join(users_dir, user))
    exp_dir = os.path.join(this_user_dir, exp_name)
    db_name = os.path.join(exp_dir, exp_name + '_' + roboid + '.db')
    if not ccbox('Please confirm the following parameters from ' + paramsfile + ': (if this isn\'t the params file you wanted, specify with 2nd argument)' +
            '\nUser name: ' + user + ('\n\n'+'\n'.join(log_banner('WELCOME NEW USER!')) + '\n' if new_user else '') +
            '\nUnique experiment name: ' + exp_name +
            '\nNumber of plates: ' + str(num_plates) +
            '\nPlate reader protocols: ' + str(protocols) +
            '\nName of database where data will be appended: \n<this directory>\\' + db_name.replace('\\', '\n\t\\')):
        exit()
    create_if_needed(exp_dir)

    with open(os.path.join(exp_dir, exp_name + '_params.cfg'), 'w+') as f:
        with open(paramsfile) as pf:
            f.write(pf.read()) # save copy of param configuration
            f.write('\n\nRobot used for this experiment: ' + roboid)

    for banner_line in log_banner('Begin execution of ' + __file__):
        logging.info(banner_line)
        
    layfile = os.path.join(this_file_dir, 'kinetics_monitoring.lay')
    lmgr = LayoutManager(layfile)

    reader_tray = lmgr.assign_unused_resource(ResourceType(Plate96, 'reader_tray_' + roboid))
    rplate_prfx = 'reader_plate_'
    # Order by integer suffix because plate 10 is before plate 2 lexicographically:
    reader_plates = resource_list_with_prefix(lmgr, rplate_prfx, Plate96, num_plates, order_key=lambda p: int(p.layout_name()[len(rplate_prfx):]))
    print('Plates are ', [p.layout_name() for p in reader_plates])

    for p in reader_plates:
        logging.info(p)

    simulation_on = '--simulate' in sys.argv

    with HamiltonInterface(simulate=simulation_on) as ham_int, ClarioStar() as reader_int:
        if simulation_on:
            reader_int.disable()
        ham_int.set_log_dir(os.path.join(local_log_dir, roboid + '_hamilton.log'))
        initialize(ham_int)
        if not simulation_on:
            hepa_on(ham_int, speed=20)
        
        # loop over plates and read them
        while True:
            for plate in reader_plates:
                try:
                    platedata = read_plate(ham_int, reader_int, reader_tray, plate, protocols, plate_id=plate.layout_name())
                    if simulation_on:
                        platedata = [PlateData(os.path.join(reader_results_dir, '17_8_12_abs_180426_1910.csv'))]*len(protocols) # sim dummy
                    for i in range(len(protocols)):
                        db_add_plate_data(db_name, platedata[i], protocols[i], plate)
                except oemerr.LabwareError:
                    print ("Skipping this plate", plate.layout_name())
