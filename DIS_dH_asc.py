#Python v3.13.13
import numpy as np  #numpy==2.4.6
#Get base folder for outputs
Basepath = "F:\\cauvery_Update\\2026_cauvery_project\\GW\\output\\"

#Get Baseline run number
BaseRun = "cauvery401"
#Get Scenario run number
ScenRen = "cauvery405"

#Get list of stress periods asc's have been extracted for
sp_list = [1667, 1179, 1308] 
# Get number of layers asc would have been extracted for
NLAY = 3                #Layers

for i in range (len(sp_list)):
        for Lay in range (0,NLAY):
            #Read asci files to find the difference for
            file1path = Basepath+str(BaseRun)+"\\"+"heads\\"+str(BaseRun)+"_heads_L"+ str(Lay+1) + "_SP"+str(sp_list[i])+".asc"
            file2path = Basepath+str(ScenRen)+"\\"+"heads\\"+str(ScenRen)+"_heads_L"+ str(Lay+1) + "_SP"+str(sp_list[i])+".asc"
            out_file = Basepath+str(ScenRen)+"\\heads\\"+ "dh_"+str(BaseRun)+"-"+str(ScenRen)+"_L"+str(Lay+1) +"_SP"+str(sp_list[i])+".asc"

            #As for same model, header will be the same, so pick first header to later apply to the difference asc file
            with open(file1path, "r") as f:
                first_six_lines = [next(f) for _ in range(6)]

            #Load up data from the individual asci files
            asc_data1 = np.loadtxt(file1path, skiprows=6)
            asc_data2 = np.loadtxt(file2path, skiprows=6)
            diff = asc_data1 - asc_data2

            nodata = 1e30               ### MF6 no data value (HNOFLO = 1e30 inactive; dry cells also set to 1e30 in heads extraction)

            bad = (np.abs(asc_data1) >= 1e29) | (np.abs(asc_data2) >= 1e29)     ### inactive (1e30) or dry (-1e30) in either raster
            diff[bad] = nodata                                                   ### if a cell is inactive or dry in either run, the difference becomes no data
            
            
            # Save output
            with open(out_file, "w") as f:
                # Write header
                f.writelines(first_six_lines)
                # Write raster data, 3 decimal places
                np.savetxt(f, diff,fmt="%.3f")


