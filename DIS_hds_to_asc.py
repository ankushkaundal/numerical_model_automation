#Python v3.13.13
import os
import numpy as np  #numpy==2.4.6
import flopy        #flopy==3.10.0


#Load up groundwater model parameters - DIS
CellSize = 200          #Cellsize
NLAY = 3                #Layers
NROW = 335              #Number of rows (NROW)
NCOL = 406              #Number of columns (NCOL)
XORIGIN = 499000        #Grid origins - X (Easting) 
YORIGIN = 150000        #Grid origins - Y (Northing)

#Bring up Run Number (other aspects like file path will auto update)
RunNo = "cauvery405"

#Set out base location of outputs 
outfolder = "F:\\cauvery_Update\\2026_cauvery_project\\GW\\output\\" 

# Location of heads file 
headfile = outfolder + RunNo +"\\" + RunNo + ".hds"
mhds = flopy.utils.HeadFile(headfile)

#List stress period/s to get data - can be expanded to as many stress periods as needed
sp_list = [1667, 1179, 1308] 

#Set timestep for end of stress period 
time_step = 1

# output ASC grids, sper, time_step - stress period and time step number [enhancing EA examples from ESS model] 
#
for i in range (len(sp_list)):
        for Lay in range (0,NLAY):
                hds = mhds.get_data(kstpkper=(time_step - 1, sp_list[i] - 1), mflay = Lay)
                
                hds[hds <= -1e29] = 1e30    ### Convert MF6 dry cells (-1e30) to inactive value (1e30) so both match NODATA_value
                
                # Header for .asc grids
                header = "ncols           " + str(NCOL) +"\n"
                header += "nrows          " + str(NROW) + "\n"
                header += "xllcorner      " + str(XORIGIN) + "\n"
                header += "yllcorner      " + str(YORIGIN) + "\n"
                header += "cellsize       " + str(CellSize) + "\n"
                #1000000000000000019884624838656.000 is the mf6 no data value that gets saved to the hds file
                header += "NODATA_value   1000000000000000019884624838656.000"
                # save .asc grids with GW levels
                np.savetxt(outfolder + RunNo + "\\heads\\"+"{}_heads_L{}_SP{}.asc".format(RunNo,str(Lay + 1),sp_list[i]), hds, header=header, fmt="%1.3f", comments='')





