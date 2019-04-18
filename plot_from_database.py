import sqlite3
import matplotlib.pyplot as plt
from datetime import datetime
import sys, os
import math
import csv
try:
    from easygui import msgbox
except Exception:
    def msgbox(_):
        pass
from tkinter import Tk
from tkinter.filedialog import askopenfilename

number_of_turb = 96

if len(sys.argv) < 2:
    msg = 'Must supply user name as first argument.'
    print(msg)
    msgbox(msg)
    exit()
user = sys.argv[1]
if not any((user.upper() == u.upper() for u in os.listdir('Users'))):
    msg = 'User name ' + user + ' not recognized. These are the users I know:\n\n' + '\n'.join(os.listdir('Users'))
    print(msg)
    msgbox(msg)
    exit()

this_user_dir = os.path.abspath('Users/' + user)
def filepaths(directory):
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            yield os.path.join(root, filename)
dbs = (filepath for filepath in filepaths(this_user_dir)
        if filepath.lower().endswith('.db'))
latest = max(dbs, key=os.path.getctime)
Tk().withdraw() # keep the window from appearing
db_name = askopenfilename(initialdir=os.path.dirname(latest), title="Select database file", filetypes=((".db files","*.db"),("all files","*.*")))
if not db_name:
    print('Cancel.')
    exit()

conn = sqlite3.connect(db_name)
c = conn.cursor()
try:
    c.execute('select count(distinct plate_id) from measurements')
except sqlite3.OperationalError:
    msg = 'Selected database doesn\'t have a "measurements" table.'
    print(msg)
    msgbox(msg)
    exit()
num_plates, = c.fetchone()
c.execute('select distinct data_type from measurements')
protocols = [p for p, in c.fetchall()]

print('\n** Database: ' + os.path.basename(db_name) + ' **\n')

def create_if_needed(dirname):
    if not os.path.exists(dirname):
        os.mkdir(dirname)
    return dirname

for plate in range(1, num_plates+1):
    for type in protocols:
        
        print("Processing plate", plate, "type", type)
        
        # collect csv data to file
        csv_data = [] 
        
        scale = 1
        fig1 = plt.figure(figsize=(24*scale, 16*scale))
        subplot = 0
        for row in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
            for column in range(1, 12+1):
                well = row+str(column)
                subplot = subplot + 1
                # set up plot
                ax = fig1.add_subplot(8, number_of_turb/8, subplot)
                ax.set_title("Well" + well, x=0.5, y=0.8)
        
                n = ('reader_plate_' + str(plate), well, type, )
                c.execute('SELECT filename, well, reading FROM measurements WHERE plate_id=? AND well=? AND data_type=?', n)
                readings_list = c.fetchall()
                if len(readings_list) == 0:
                    conn.close()
                    exit()
                vals = [(datetime.strptime(f[-15:-4], '%y%m%d_%H%M'), w, v) for (f, w, v) in readings_list]
                vals = [(t, w, v) for t, w, v in vals if t > datetime(2018, 11, 7, 21, 15)] 
                
                # plot
                plt.plot([j for (j, _, _) in vals], [lum for (j, _, lum) in vals], 'b.')
    
                # common axis limits for all subplots
                if 'abs' in type:
                    plt.ylim(0.0, 1.0)
                else:
                    plt.ylim(0.0, 100000.0)
                
                # decrease number of plotted X axis labels
                # make there be fewer labels so that you can read them
                times = [x for (x, _, _) in vals]
                deltas = [t - times[0] for t in times]
                labels = [int(d.seconds/60/60 + d.days*24) for d in deltas]
                labels_sparse = [labels[x] if x % 12 == 0 else '' for x in range(len(labels))]
                plt.xticks(times, labels_sparse)
                locs, labels = plt.xticks()
                
                # collect csv data
                if(well == 'A1'):
                   csv_data.append(['Time'] + [t for (t, _, _) in vals])
                correct_well_name = well[0]+str(well[1:]).zfill(2) # three characters
                csv_data.append([correct_well_name] + [v for (_, _, v) in vals])
        print(len(readings_list), "entries fetched")
    
        fig1.tight_layout()
        graphs_dir = create_if_needed(os.path.abspath(os.path.join(os.path.dirname(db_name), 'graphs')))
        plt.savefig(os.path.join(graphs_dir, os.path.basename(db_name)[:-3]+'_plate' + str(plate) + "_" + type + ".png"), dpi = 200)
        plt.close(fig1)
        
        # write data to a file
        csvs_dir = create_if_needed(os.path.join(os.path.dirname(db_name), 'spreadsheets'))
        csvfile = open(os.path.join(csvs_dir, os.path.basename(db_name)[:-3]+'_reader_plate_' + str(plate)+"_"+type+'.csv'), 'w')
        csvwriter = csv.writer(csvfile)
        for d in csv_data:
            csvwriter.writerow(d)    
        csvfile.close()  

conn.close()


