import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import scipy.interpolate
from scipy.spatial import distance
from scipy import ndimage
from PIL import Image, ImageDraw
from skimage import measure
from skimage import morphology
from matplotlib.colors import LinearSegmentedColormap
from ipywidgets import FloatProgress
from IPython.display import display
import numba
import matplotlib.colors as mcolors
import matplotlib.gridspec as gridspec

class Channel:
    """class for Channel objects"""
    def __init__(self,x,y,z,W,D):
        """initialize Channel object
        x, y, z  - coordinates of centerline
        W - channel width
        D - channel depth"""
        self.x = x
        self.y = y
        self.z = z
        self.W = W
        self.D = D

class Cutoff:
    """class for Cutoff objects"""
    def __init__(self,x,y,z,W,D):
        """initialize Cutoff object
        x, y, z  - coordinates of centerline
        W - channel width
        D - channel depth"""
        self.x = x
        self.y = y
        self.z = z
        self.W = W
        self.D = D

class ChannelBelt3D:
    """class for 3D models of channel belts"""
    def __init__(self, model_type, topo, strat, facies, facies_code, dx, channels):
        self.model_type = model_type
        self.topo = topo
        self.strat = strat
        self.facies = facies
        self.dx = dx
        self.channels = channels

    def plot_xsection(self, xsec, colors, ve):
        # colors = [[0.5,0.25,0],[0.9,0.9,0],[0.5,0.25,0]]
        strat = self.strat
        dx = self.dx
        fig1 = plt.figure(figsize=(20,5))
        ax1 = fig1.add_subplot(111)
        r,c,ts = np.shape(strat)
        Xv = dx * np.arange(0,r)
        for xloc in range(xsec,xsec+1,1):
            # ax1.cla()
            # ax2.cla()
            # ax3.cla()
            for i in range(0,ts-1,3):
                X1 = np.concatenate((Xv, Xv[::-1]))  
                Y1 = np.concatenate((strat[:,xloc,i], strat[::-1,xloc,i+1])) 
                Y2 = np.concatenate((strat[:,xloc,i+1], strat[::-1,xloc,i+2]))
                Y3 = np.concatenate((strat[:,xloc,i+2], strat[::-1,xloc,i+3]))
                if self.model_type == 'submarine':
                    ax1.fill(X1, Y1, facecolor=colors[2], linewidth=0.5, edgecolor=[0,0,0]) # oxbow mud
                    ax1.fill(X1, Y2, facecolor=colors[0], linewidth=0.5, edgecolor=[0,0,0]) # point bar sand
                    ax1.fill(X1, Y3, facecolor=colors[1], linewidth=0.5) # levee mud
                if self.model_type == 'fluvial':
                    ax1.fill(X1, Y1, facecolor=colors[0], linewidth=0.5, edgecolor=[0,0,0]) # levee mud
                    ax1.fill(X1, Y2, facecolor=colors[1], linewidth=0.5, edgecolor=[0,0,0]) # oxbow mud
                    ax1.fill(X1, Y3, facecolor=colors[2], linewidth=0.5) # channel sand
            ax1.set_xlim(0,dx*(r-1))
            ax1.set_aspect(ve, adjustable='datalim')
        fig2 = plt.figure()
        ax2 = fig2.add_subplot(111)
        ax2.contourf(strat[:,:,ts-1],100,cmap='viridis')
        # ax2.contour(strat[:,:,ts-1],100,colors='k',linestyles='solid',linewidth=0.1,alpha=0.4)
        ax2.plot([xloc, xloc],[0,r],'k',linewidth=2)
        ax2.axis([0,c,0,r])
        ax2.set_aspect('equal', adjustable='box')        
        ax2.set_title('final geomorphic surface')
        ax2.tick_params(bottom=False,top=False,left=False,right=False,labelbottom=False,labelleft=False)
        fig3 = plt.figure()
        ax3 = fig3.add_subplot(111)
        ax3.contourf(strat[:,:,0],100,cmap='viridis')
        # ax3.contour(strat[:,:,0],100,colors='k',linestyles='solid',linewidth=0.1,alpha=0.4)
        ax3.plot([xloc, xloc],[0,r],'k',linewidth=2)
        ax3.axis([0,c,0,r])
        ax3.set_aspect('equal', adjustable='box')
        ax3.set_title('basal erosional surface')
        ax3.tick_params(bottom=False,top=False,left=False,right=False,labelbottom=False,labelleft=False)
        return fig1,fig2,fig3

class ChannelBelt:
    """class for ChannelBelt objects"""
    def __init__(self, channels, cutoffs, cl_times, cutoff_times):
        """initialize ChannelBelt object
        channels - list of Channel objects
        cutoffs - list of Cutoff objects
        cl_times - list of ages of Channel objects
        cutoff_times - list of ages of Cutoff objects"""
        self.channels = channels
        self.cutoffs = cutoffs
        self.cl_times = cl_times
        self.cutoff_times = cutoff_times

    def migrate(self,nit,saved_ts,deltas,pad,crdist,Cf,kl,kv,dt,dens,t1,t2,t3,aggr_factor,*D):
        """function for computing migration rates along channel centerlines and moving the centerlines accordingly
        inputs:
        nit - number of iterations
        saved_ts - which time steps will be saved
        deltas - distance between nodes on centerline
        pad - padding (number of nodepoints along centerline)
        crdist - threshold distance at which cutoffs occur
        Cf - dimensionless Chezy friction factor
        kl - migration rate constant (m/s)
        kv - vertical slope-dependent erosion rate constant (m/s)
        dt - time step (s)
        dens - density of fluid (kg/m3)
        t1 - time step when incision starts
        t2 - time step when lateral migration starts
        t3 - time step when aggradation starts
        aggr_factor - aggradation factor
        D - channel depth"""
        channel = self.channels[-1] # first channel is the same as last channel of input
        x = channel.x; y = channel.y; z = channel.z
        W = channel.W;
        if len(D)==0: 
            D = channel.D
        else:
            D = D[0]
        k = 1.0 # constant in HK equation
        xc = [] # initialize cutoff coordinates
        # determine age of last channel:
        if len(self.cl_times)>0:
            last_cl_time = self.cl_times[-1]
        else:
            last_cl_time = 0
        dx, dy, dz, ds, s = compute_derivatives(x,y,z)
        slope = np.gradient(z)/ds
        # padding at the beginning can be shorter than padding at the downstream end:
        pad1 = int(pad/10.0)
        if pad1<5:
            pad1 = 5
        omega = -1.0 # constant in curvature calculation (Howard and Knutson, 1984)
        gamma = 2.5 # from Ikeda et al., 1981 and Howard and Knutson, 1984
        f = FloatProgress(min=1,max=nit) # progress bar
        display(f)
        for itn in range(nit): # main loop
            f.value += 1
            ns=len(x)
            dx, dy, ds, s, curv = compute_curvature(x,y)
            curv = W*curv # dimensionless curvature
            R0 = kl*curv # simple linear relationship between curvature and nominal migration rate
            alpha = k*2*Cf/D # exponent for convolution function G
            R1 = compute_migration_rate(pad,ns,ds,alpha,omega,gamma,R0)
            # calculate new centerline coordinates:
            dy_ds = dy[pad1:ns-pad+1]/ds[pad1:ns-pad+1]
            dx_ds = dx[pad1:ns-pad+1]/ds[pad1:ns-pad+1]
            # adjust x and y coordinates (this *is* the migration):
            x[pad1:ns-pad+1] = x[pad1:ns-pad+1] + R1[pad1:ns-pad+1]*dy_ds*dt  
            y[pad1:ns-pad+1] = y[pad1:ns-pad+1] - R1[pad1:ns-pad+1]*dx_ds*dt 
            # find and execute cutoffs:
            x,y,z,xc,yc,zc = cut_off_cutoffs(x,y,z,s,crdist,deltas) 
            dx, dy, ds, dz, s = compute_derivatives(x,y,z) # recompute derivatives
            # resample centerline so that 'deltas' is roughly constant
            # [parametric spline representation of curve; note that there is *no* smoothing]
            tck, u = scipy.interpolate.splprep([x,y,z],s=0) 
            unew = np.linspace(0,1,1+s[-1]/deltas) # vector for resampling
            out = scipy.interpolate.splev(unew,tck) # resampling
            x, y, z = out[0], out[1], out[2] # assign new coordinate values
            # z = np.minimum.accumulate(z)
            dx, dy, dz, ds, s = compute_derivatives(x,y,z) # recompute derivatives
            # incision:
            slope = np.gradient(z)/ds
            # slope-dependent erosion:
            if (itn>t1) & (itn<=t2):
                if np.min(np.abs(slope))!=0:
                    z = z + kv*dens*9.81*D*slope*dt # slope-dependent incision
                else:
                    z = z - 0.005*4
            if (itn>t2) & (itn<=t3): # lateral migration
                if np.min(np.abs(slope))!=0:
                    z = z + kv*dens*9.81*D*slope*dt - kv*dens*9.81*D*np.median(slope)*dt
                else:
                    z = z
            if (itn>t3): # aggradation
                if np.min(np.abs(slope))!=0:
                    z = z + kv*dens*9.81*D*slope*dt - aggr_factor*kv*dens*9.81*D*np.mean(slope)*dt 
                else:
                    z = z + 0.005*4
            if len(xc)>0: # save cutoff data
                self.cutoff_times.append(last_cl_time+(itn+1)*dt/(365*24*60*60.0))
                cutoff = Cutoff(xc,yc,zc,W,D) # create cutoff object
                self.cutoffs.append(cutoff)
            # saving centerlines:
            if np.mod(itn,saved_ts)==0:
                self.cl_times.append(last_cl_time+(itn+1)*dt/(365*24*60*60.0))
                channel = Channel(x,y,z,W,D) # create channel object
                self.channels.append(channel)

    def plot(self,plot_type,pb_age,ob_age,*end_time):
        """plot ChannelBelt object
        plot_type - can be either 'strat' (for stratigraphic plot) or 'morph' (for morphologic plot)
        pb_age - age of point bars (in years) at which they get covered by vegetation
        ob_age - age of oxbow lakes (in years) at which they get covered by vegetation
        end_time (optional) - age of last channel to be plotted (in years)"""
        cot = np.array(self.cutoff_times)
        sclt = np.array(self.cl_times)
        if len(end_time)>0:
            cot = cot[cot<=end_time]
            sclt = sclt[sclt<=end_time]
        times = np.sort(np.hstack((cot,sclt)))
        times = np.unique(times)
        order = 0 # variable for ordering objects in plot
        # set up min and max x and y coordinates of the plot:
        xmin = np.min(self.channels[0].x)
        xmax = np.max(self.channels[0].x)
        ymax = 0
        for i in range(len(self.channels)):
            ymax = max(ymax, np.max(np.abs(self.channels[i].y)))
        ymax = ymax+2*self.channels[0].W # add a bit of space on top and bottom
        ymin = -1*ymax
        # size figure so that its size matches the size of the model:
        fig = plt.figure(figsize=(20,(ymax-ymin)*20/(xmax-xmin))) 
        if plot_type == 'morph':
            pb_crit = len(times[times<times[-1]-pb_age])/float(len(times))
            ob_crit = len(times[times<times[-1]-ob_age])/float(len(times))
            green = (106/255.0,159/255.0,67/255.0) # vegetation color
            pb_color = (189/255.0,153/255.0,148/255.0) # point bar color
            ob_color = (15/255.0,58/255.0,65/255.0) # oxbow color
            pb_cmap = make_colormap([green,green,pb_crit,green,pb_color,1.0,pb_color]) # colormap for point bars
            ob_cmap = make_colormap([green,green,ob_crit,green,ob_color,1.0,ob_color]) # colormap for oxbows
            plt.fill([xmin,xmax,xmax,xmin],[ymin,ymin,ymax,ymax],color=(106/255.0,159/255.0,67/255.0))
        for i in range(0,len(times)):
            if times[i] in sclt:
                ind = np.where(sclt==times[i])[0][0]
                x1 = self.channels[ind].x
                y1 = self.channels[ind].y
                W = self.channels[ind].W
                xm, ym = get_channel_banks(x1,y1,W)
                if plot_type == 'morph':
                    if times[i]>times[-1]-pb_age:
                        plt.fill(xm,ym,facecolor=pb_cmap(i/float(len(times)-1)),edgecolor='k',linewidth=0.2)
                    else:
                        plt.fill(xm,ym,facecolor=pb_cmap(i/float(len(times)-1)))
                else:
                    order = order+1
                    plt.fill(xm,ym,sns.xkcd_rgb["light tan"],edgecolor='k',linewidth=0.25,zorder=order)
            if times[i] in cot:
                ind = np.where(cot==times[i])[0][0]
                for j in range(0,len(self.cutoffs[ind].x)):
                    x1 = self.cutoffs[ind].x[j]
                    y1 = self.cutoffs[ind].y[j]
                    xm, ym = get_channel_banks(x1,y1,self.cutoffs[ind].W)
                    if plot_type == 'morph':
                        plt.fill(xm,ym,color=ob_cmap(i/float(len(times)-1)))
                    else:
                        order = order+1
                        plt.fill(xm,ym,sns.xkcd_rgb["ocean blue"],edgecolor='k',linewidth=0.25,zorder=order)
        x1 = self.channels[len(sclt)-1].x
        y1 = self.channels[len(sclt)-1].y
        xm, ym = get_channel_banks(x1,y1,self.channels[len(sclt)-1].W)
        order = order+1
        plt.fill(xm,ym,color=(16/255.0,73/255.0,90/255.0),zorder=order) #,edgecolor='k')
        plt.axis('equal')
        plt.xlim(xmin,xmax)
        plt.ylim(ymin,ymax)
        return fig

    def create_movie(self,xmin,xmax,plot_type,filename,dirname,pb_age,ob_age,scale,*end_time):
        """method for creating movie frames (PNG files) that capture the plan-view evolution of a channel belt through time
        movie has to be assembled from the PNG file after this method is applied
        xmin - value of x coodinate on the left side of frame
        xmax - value of x coordinate on right side of frame
        plot_type = - can be either 'strat' (for stratigraphic plot) or 'morph' (for morphologic plot)
        filename - first few characters of the output filenames
        dirname - name of directory where output files should be written
        pb_age - age of point bars (in years) at which they get covered by vegetation (if the 'morph' option is used for 'plot_type')
        ob_age - age of oxbow lakes (in years) at which they get covered by vegetation (if the 'morph' option is used for 'plot_type')
        scale - scaling factor (e.g., 2) that determines how many times larger you want the frame to be, compared to the default scaling of the figure
        """
        sclt = np.array(self.cl_times)
        if len(end_time)>0:
            sclt = sclt[sclt<=end_time]
        channels = self.channels[:len(sclt)]
        ymax = 0
        for i in range(len(channels)):
            ymax = max(ymax, np.max(np.abs(channels[i].y)))
        ymax = ymax+2*channels[0].W # add a bit of space on top and bottom
        ymin = -1*ymax
        for i in range(0,len(sclt)):
            fig = self.plot(plot_type,pb_age,ob_age,sclt[i])
            fig_height = scale*fig.get_figheight()
            fig_width = (xmax-xmin)*fig_height/(ymax-ymin)
            fig.set_figwidth(fig_width)
            fig.set_figheight(fig_height)
            fig.gca().set_xlim(xmin,xmax)
            fig.gca().set_xticks([])
            fig.gca().set_yticks([])
            plt.plot([xmin+200, xmin+200+5000],[ymin+200, ymin+200], 'k', linewidth=2)
            plt.text(xmin+200+2000, ymin+200+100, '5 km', fontsize=14)
            fname = dirname+filename+'%03d.png'%(i)
            fig.savefig(fname, bbox_inches='tight')
            plt.close()

    def build_3d_model(self,model_type,h_mud,levee_width,h,w,bth,dcr,dx,delta_s,starttime,endtime,xmin,xmax,ymin,ymax):
        """method for building 3D model from set of centerlines (that are part of a ChannelBelt object)
        Inputs: 
        model_type - model type ('fluvial' or 'submarine')
        h_mud - maximum thickness of overbank mud
        levee_width - width of overbank mud
        h - channel depth
        w - channel width
        bth - thickness of channel sand (only used in submarine models)
        dcr - critical channel depth where sand thickness goes to zero (only used in submarine models)
        dx - cell size in x and y directions
        delta_s - sampling distance alogn centerlines
        starttime - 
        endtime -
        Returns: a ChannelBelt3D object
        """
        sclt = np.array(self.cl_times)
        ind1 = np.where(sclt>=starttime)[0][0] 
        ind2 = np.where(sclt<=endtime)[0][-1]
        sclt = sclt[ind1:ind2+1]
        channels = self.channels[ind1:ind2+1]
        cot = np.array(self.cutoff_times)
        if (len(cot)>0) & (len(np.where(cot>=starttime)[0])>0) & (len(np.where(cot<=endtime)[0])>0):
            cfind1 = np.where(cot>=starttime)[0][0] 
            cfind2 = np.where(cot<=endtime)[0][-1]
            cot = cot[cfind1:cfind2+1]
            cutoffs = self.cutoffs[cfind1:cfind2+1]
        else:
            cot = []
            cutoffs = []
        n_steps = len(sclt) # number of events
        if xmin == 0: # plot centerlines and define model domain
            plt.figure(figsize=(15,4))
            maxX, minY, maxY = 0, 0, 0
            for i in range(n_steps): # plot centerlines
                plt.plot(channels[i].x,channels[i].y,'k')
                maxX = max(maxX,np.max(channels[i].x))
                maxY = max(maxY,np.max(channels[i].y))
                minY = min(minY,np.min(channels[i].y))
            plt.axis([0,maxX,minY-10*w,maxY+10*w])
            plt.gca().set_aspect('equal', adjustable='box')
            plt.tight_layout()
            pts = np.zeros((2,2))
            for i in range(0,2):
                pt = np.asarray(plt.ginput(1))
                pts[i,:] = pt
                plt.scatter(pt[0][0],pt[0][1])
            plt.plot([pts[0,0],pts[1,0],pts[1,0],pts[0,0],pts[0,0]],[pts[0,1],pts[0,1],pts[1,1],pts[1,1],pts[0,1]],'r')
            xmin = min(pts[0,0],pts[1,0])
            xmax = max(pts[0,0],pts[1,0])
            ymin = min(pts[0,1],pts[1,1])
            ymax = max(pts[0,1],pts[1,1])
        iwidth = int((xmax-xmin)/dx)
        iheight = int((ymax-ymin)/dx)
        topo = np.zeros((iheight,iwidth,4*n_steps)) # array for storing topographic surfaces
        facies = np.zeros((iheight-1,iwidth-1,4*n_steps)) # array for storing facies
        # create initial topography:
        x1 = np.linspace(0,iwidth-1,iwidth)
        y1 = np.linspace(0,iheight-1,iheight)
        xv, yv = np.meshgrid(x1,y1)
        z1 = channels[0].z
        z1 = z1[(channels[0].x>xmin) & (channels[0].x<xmax)]
        topoinit = z1[0] - ((z1[0]-z1[-1])/(xmax-xmin))*xv*dx # initial (sloped) topography
        topo[:,:,0] = topoinit.copy()
        surf = topoinit.copy()
        facies[:,:,0] = np.NaN
        # generate surfaces:
        f = FloatProgress(min=0,max=n_steps)
        display(f)
        channels3D = []
        x_pixs = []
        y_pixs = []
        for i in range(n_steps):
            f.value += 1
            x = channels[i].x
            y = channels[i].y
            z = channels[i].z
            cutoff_ind = []
            # check if there were cutoffs during the last time step and collect indices in an array:
            for j in range(len(cot)):
                if (cot[j] >= sclt[i-1]) & (cot[j] < sclt[i]):
                    cutoff_ind = np.append(cutoff_ind,j)
            # create distance map:
            cl_dist, x_pix, y_pix, z_pix, s_pix, z_map, x1, y1, z1 = dist_map(x,y,z,xmin,xmax,ymin,ymax,dx,delta_s)
            if i == 0:
                cl_dist_prev = cl_dist
            # erosion:
            surf = np.minimum(surf,erosion_surface(h,w/dx,cl_dist,z_map))
            topo[:,:,4*i] = surf # erosional surface
            facies[:,:,4*i] = np.NaN

            if model_type == 'fluvial':
                pb = point_bar_surface(surf,cl_dist,z_map,h,w/dx)
                th = np.maximum(surf,pb)-surf
                th_oxbows = th.copy()
                # setting sand thickness to zero at cutoff locations:
                if len(cutoff_ind)>0:
                    cutoff_dists = 1e10*np.ones(np.shape(th)) #initialize cutoff_dists with a large number
                    for j in range(len(cutoff_ind)):
                        cutoff_dist, cfx_pix, cfy_pix = cl_dist_map(cutoffs[int(cutoff_ind[j])].x[0],cutoffs[int(cutoff_ind[j])].y[0],cutoffs[int(cutoff_ind[j])].z[0],xmin,xmax,ymin,ymax,dx)
                        cutoff_dists = np.minimum(cutoff_dists,cutoff_dist)
                    th_oxbows[cutoff_dists>=0.9*w/dx] = 0 # set oxbow fill thickness to zero outside of oxbows
                    th[cutoff_dists<0.9*w/dx] = 0 # set point bar thickness to zero inside of oxbows
                else: # no cutoffs
                    th_oxbows = np.zeros(np.shape(th))
                th[th<0] = 0 # eliminate negative th values
                surf = surf+th_oxbows # update topographic surface with oxbow deposit thickness
                topo[:,:,4*i+1] = surf # top of oxbow mud
                facies[:,:,4*i+1] = 0
                surf = surf+th # update topographic surface with sand thickness
                topo[:,:,4*i+2] = surf # top of sand
                facies[:,:,4*i+2] = 1
                # surf = surf + mud_surface(h_mud,levee_width/dx,cl_dist,w/dx) # mud/levee deposition
                surf = surf + mud_surface(h_mud,levee_width/dx,cl_dist,w/dx,z_map,surf)
                topo[:,:,4*i+3] = surf # top of levee
                facies[:,:,4*i+3] = 2
                channels3D.append(Channel(x1,y1,z1,w,h))
                x_pixs.append(x_pix)
                y_pixs.append(y_pix)

            if model_type == 'submarine':
                surf = surf + mud_surface(h_mud[i],levee_width/dx,cl_dist,w/dx,z_map,surf) # mud/levee deposition
                topo[:,:,4*i+1] = surf # top of levee
                facies[:,:,4*i+1] = 2
                # sand thickness:
                th, relief = sand_surface(surf,bth,dcr,cl_dist,z_map,h)
                th[th<0] = 0 # eliminate negative th values
                th[cl_dist>1.0*w/dx] = 0 # eliminate sand outside of channel
                th_oxbows = th.copy()
                # setting sand thickness to zero at cutoff locations:
                if len(cutoff_ind)>0:
                    cutoff_dists = 1e10*np.ones(np.shape(th)) #initialize cutoff_dists with a large number
                    for j in range(len(cutoff_ind)):
                        cutoff_dist, cfx_pix, cfy_pix = cl_dist_map(cutoffs[int(cutoff_ind[j])].x[0],cutoffs[int(cutoff_ind[j])].y[0],cutoffs[int(cutoff_ind[j])].z[0],xmin,xmax,ymin,ymax,dx)
                        cutoff_dists = np.minimum(cutoff_dists,cutoff_dist)
                    th_oxbows[cutoff_dists>=0.9*w/dx] = 0 # set oxbow fill thickness to zero outside of oxbows
                    th[cutoff_dists<0.9*w/dx] = 0 # set point bar thickness to zero inside of oxbows
                    # adding back sand near the channel axis (submarine only):
                    # th[cl_dist<0.5*w/dx] = bth*(1 - relief[cl_dist<0.5*w/dx]/dcr)
                else: # no cutoffs
                    th_oxbows = np.zeros(np.shape(th))
                surf = surf+th_oxbows # update topographic surface with oxbow deposit thickness
                topo[:,:,4*i+2] = surf # top of oxbow mud
                facies[:,:,4*i+2] = 0
                surf = surf+th # update topographic surface with sand thickness
                topo[:,:,4*i+3] = surf # top of sand
                facies[:,:,4*i+3] = 1

            cl_dist_prev = cl_dist.copy()
        topo = np.concatenate((np.reshape(topoinit,(iheight,iwidth,1)),topo),axis=2) # add initial topography to array
        strat = topostrat(topo) # create stratigraphic surfaces
        strat = np.delete(strat, np.arange(4*n_steps+1)[1::4], 2) # get rid of unnecessary stratigraphic surfaces (duplicates)
        facies = np.delete(facies, np.arange(4*n_steps)[::4], 2) # get rid of unnecessary facies layers (NaNs)
        if model_type == 'fluvial':
            facies_code = {0:'oxbow', 1:'point bar', 2:'levee'}
        if model_type == 'submarine':
            facies_code = {0:'levee', 1:'oxbow', 2:'channel sand'}
        chb_3d = ChannelBelt3D(model_type,topo,strat,facies,facies_code,dx,channels3D)
        return chb_3d, xmin, xmax, ymin, ymax

def generate_initial_channel(W,D,Sl,deltas,pad,n_bends):
    """generate straight Channel object with some noise added that can serve
    as input for initializing a ChannelBelt object
    W - channel width
    D - channel depth
    Sl - channel gradient
    deltas - distance between nodes on centerline
    pad - padding (number of nodepoints along centerline)
    n_bends - approximate number of bends to be simulated"""
    noisy_len = n_bends*10*W/2.0 # length of noisy part of initial centerline
    pad1 = int(pad/10.0) # padding at upstream end can be shorter than padding on downstream end
    if pad1<5:
        pad1 = 5
    x = np.linspace(0, noisy_len+(pad+pad1)*deltas, int(noisy_len/deltas+pad+pad1)+1) # x coordinate
    y = 10.0 * (2*np.random.random_sample(int(noisy_len/deltas)+1,)-1)
    y = np.hstack((np.zeros((pad1),),y,np.zeros((pad),))) # y coordinate
    deltaz = Sl * deltas*(len(x)-1)
    z = np.linspace(0,deltaz,len(x))[::-1] # z coordinate
    return Channel(x,y,z,W,D)

@numba.jit(nopython=True) # use Numba to speed up the heaviest computation
def compute_migration_rate(pad,ns,ds,alpha,omega,gamma,R0):
    """compute migration rate as weighted sum of upstream curvatures
    pad - padding (number of nodepoints along centerline)
    ns - number of points in centerline
    ds - distances between points in centerline
    omega - constant in HK model
    gamma - constant in HK model
    R0 - nominal migration rate (dimensionless curvature * migration rate constant)"""
    R1 = np.zeros(ns) # preallocate adjusted channel migration rate
    pad1 = int(pad/10.0) # padding at upstream end can be shorter than padding on downstream end
    if pad1<5:
        pad1 = 5
    for i in range(pad1,ns-pad):
        si2 = np.hstack((np.array([0]),np.cumsum(ds[i-1::-1])))  # distance along centerline, backwards from current point 
        G = np.exp(-alpha*si2) # convolution vector
        R1[i] = omega*R0[i] + gamma*np.sum(R0[i::-1]*G)/np.sum(G) # main equation
    return R1

def compute_derivatives(x,y,z):
    """function for computing first derivatives of a curve (centerline)
    x,y are cartesian coodinates of the curve
    outputs:
    dx - first derivative of x coordinate
    dy - first derivative of y coordinate
    ds - distances between consecutive points along the curve
    s - cumulative distance along the curve"""
    dx = np.gradient(x) # first derivatives
    dy = np.gradient(y)   
    dz = np.gradient(z)   
    ds = np.sqrt(dx**2+dy**2+dz**2)
    s = np.cumsum(ds)
    return dx, dy, dz, ds, s

def compute_curvature(x,y):
    """function for computing first derivatives and curvature of a curve (centerline)
    x,y are cartesian coodinates of the curve
    outputs:
    dx - first derivative of x coordinate
    dy - first derivative of y coordinate
    ds - distances between consecutive points along the curve
    s - cumulative distance along the curve
    curvature - curvature of the curve (in 1/units of x and y)"""
    dx = np.gradient(x) # first derivatives
    dy = np.gradient(y)      
    ds = np.sqrt(dx**2+dy**2)
    ddx = np.gradient(dx) # second derivatives 
    ddy = np.gradient(dy) 
    curvature = (dx*ddy - dy*ddx) / ((dx**2 + dy**2)**1.5)
    s = np.cumsum(ds)
    return dx, dy, ds, s, curvature

def make_colormap(seq):
    """Return a LinearSegmentedColormap
    seq: a sequence of floats and RGB-tuples. The floats should be increasing
    and in the interval (0,1).
    [from: https://stackoverflow.com/questions/16834861/create-own-colormap-using-matplotlib-and-plot-color-scale]
    """
    seq = [(None,) * 3, 0.0] + list(seq) + [1.0, (None,) * 3]
    cdict = {'red': [], 'green': [], 'blue': []}
    for i, item in enumerate(seq):
        if isinstance(item, float):
            r1, g1, b1 = seq[i - 1]
            r2, g2, b2 = seq[i + 1]
            cdict['red'].append([item, r1, r2])
            cdict['green'].append([item, g1, g2])
            cdict['blue'].append([item, b1, b2])
    return mcolors.LinearSegmentedColormap('CustomMap', cdict)

def kth_diag_indices(a,k):
    """function for finding diagonal indices with k offset (from Stackexchange)"""
    rows, cols = np.diag_indices_from(a)
    if k<0:
        return rows[:k], cols[-k:]
    elif k>0:
        return rows[k:], cols[:-k]
    else:
        return rows, cols
    
def find_cutoffs(x,y,crdist,deltas):
    """function for identifying locations of cutoffs along a centerline
    and the indices of the segments that will become part of the oxbows
    x,y - coordinates of centerline
    crdist - critical cutoff distance
    deltas - distance between neighboring points along the centerline"""
    diag_blank_width = int((crdist+20*deltas)/deltas)
    # distance matrix for centerline points:
    dist = distance.cdist(np.array([x,y]).T,np.array([x,y]).T)
    dist[dist>crdist] = np.NaN # set all values that are larger than the cutoff threshold to NaN
    # set matrix to NaN along the diagonal zone:
    for k in range(-diag_blank_width,diag_blank_width+1):
        rows, cols = kth_diag_indices(dist,k)
        dist[rows,cols] = np.NaN
    i1, i2 = np.where(~np.isnan(dist))
    ind1 = i1[np.where(i1<i2)[0]] # get rid of unnecessary indices
    ind2 = i2[np.where(i1<i2)[0]] # get rid of unnecessary indices
    return ind1, ind2 # return indices of cutoff points and cutoff coordinates

def cut_off_cutoffs(x,y,z,s,crdist,deltas):
    """function for executing cutoffs - removing oxbows from centerline and storing cutoff coordinates
    x,y - coordinates of centerline
    crdist - critical cutoff distance
    deltas - distance between neighboring points along the centerline
    outputs:
    x,y,z - updated coordinates of centerline
    xc, yc, zc - lists with coordinates of cutoff segments"""
    xc = []
    yc = []
    zc = []
    ind1, ind2 = find_cutoffs(x,y,crdist,deltas) # initial check for cutoffs
    while len(ind1)>0:
        xc.append(x[ind1[0]:ind2[0]+1]) # x coordinates of cutoff
        yc.append(y[ind1[0]:ind2[0]+1]) # y coordinates of cutoff
        zc.append(z[ind1[0]:ind2[0]+1]) # z coordinates of cutoff
        x = np.hstack((x[:ind1[0]+1],x[ind2[0]:])) # x coordinates after cutoff
        y = np.hstack((y[:ind1[0]+1],y[ind2[0]:])) # y coordinates after cutoff
        z = np.hstack((z[:ind1[0]+1],z[ind2[0]:])) # z coordinates after cutoff
        ind1, ind2 = find_cutoffs(x,y,crdist,deltas)       
    return x,y,z,xc,yc,zc

def get_channel_banks(x,y,W):
    """function for finding coordinates of channel banks, given a centerline and a channel width
    x,y - coordinates of centerline
    W - channel width
    outputs:
    xm, ym - coordinates of channel banks (both left and right banks)"""
    x1 = x.copy()
    y1 = y.copy()
    x2 = x.copy()
    y2 = y.copy()
    ns = len(x)
    dx = np.diff(x); dy = np.diff(y) 
    ds = np.sqrt(dx**2+dy**2)
    x1[:-1] = x[:-1] + 0.5*W*np.diff(y)/ds
    y1[:-1] = y[:-1] - 0.5*W*np.diff(x)/ds
    x2[:-1] = x[:-1] - 0.5*W*np.diff(y)/ds
    y2[:-1] = y[:-1] + 0.5*W*np.diff(x)/ds
    x1[ns-1] = x[ns-1] + 0.5*W*(y[ns-1]-y[ns-2])/ds[ns-2]
    y1[ns-1] = y[ns-1] - 0.5*W*(x[ns-1]-x[ns-2])/ds[ns-2]
    x2[ns-1] = x[ns-1] - 0.5*W*(y[ns-1]-y[ns-2])/ds[ns-2]
    y2[ns-1] = y[ns-1] + 0.5*W*(x[ns-1]-x[ns-2])/ds[ns-2]
    xm = np.hstack((x1,x2[::-1]))
    ym = np.hstack((y1,y2[::-1]))
    return xm, ym

def dist_map(x,y,z,xmin,xmax,ymin,ymax,dx,delta_s):
    # function for centerline rasterization and distance map calculation
    y = y[(x>xmin) & (x<xmax)]
    z = z[(x>xmin) & (x<xmax)]
    x = x[(x>xmin) & (x<xmax)] 
    dummy,dy,dz,ds,s = compute_derivatives(x,y,z)
    if len(np.where(ds>2*delta_s)[0])>0:
        inds = np.where(ds>2*delta_s)[0]
        inds = np.hstack((0,inds,len(x)))
        lengths = np.diff(inds)
        long_segment = np.where(lengths==max(lengths))[0][0]
        start_ind = inds[long_segment]+1
        end_ind = inds[long_segment+1]
        if end_ind<len(x):
            x = x[start_ind:end_ind]
            y = y[start_ind:end_ind]
            z = z[start_ind:end_ind] 
        else:
            x = x[start_ind:]
            y = y[start_ind:]
            z = z[start_ind:]
    xdist = xmax - xmin
    ydist = ymax - ymin
    iwidth = int((xmax-xmin)/dx)
    iheight = int((ymax-ymin)/dx)
    xratio = iwidth/xdist
    # create list with pixel coordinates:
    pixels = []
    for i in range(0,len(x)):
        px = int(iwidth - (xmax - x[i]) * xratio)
        py = int(iheight - (ymax - y[i]) * xratio)
        pixels.append((px,py))
    # create image and numpy array:
    img = Image.new("RGB", (iwidth, iheight), "white")
    draw = ImageDraw.Draw(img)
    draw.line(pixels, fill="rgb(0, 0, 0)") # draw centerline as black line
    pix = np.array(img)
    cl = pix[:,:,0]
    cl[cl==255] = 1 # set background to 1 (centerline is 0)
    y_pix,x_pix = np.where(cl==0) 
    x_pix,y_pix = order_cl_pixels(x_pix,y_pix)
    # This next block of code is kind of a hack. Looking for, and eliminating, 'bad' pixels.
    img = np.array(img)
    img = img[:,:,0]
    img[img==255] = 1 
    img1 = morphology.binary_dilation(img, morphology.square(2)).astype(np.uint8)
    if len(np.where(img1==0)[0])>0:
        x_pix, y_pix = eliminate_bad_pixels(img,img1)
        x_pix,y_pix = order_cl_pixels(x_pix,y_pix) 
    img1 = morphology.binary_dilation(img, np.array([[1,0,1],[1,1,1]],dtype=np.uint8)).astype(np.uint8)
    if len(np.where(img1==0)[0])>0:
        x_pix, y_pix = eliminate_bad_pixels(img,img1)
        x_pix,y_pix = order_cl_pixels(x_pix,y_pix)
    img1 = morphology.binary_dilation(img, np.array([[1,0,1],[0,1,0],[1,0,1]],dtype=np.uint8)).astype(np.uint8)
    if len(np.where(img1==0)[0])>0:
        x_pix, y_pix = eliminate_bad_pixels(img,img1)
        x_pix,y_pix = order_cl_pixels(x_pix,y_pix)
    #redo the distance calculation (because x_pix and y_pix do not always contain all the points in cl):
    cl[cl==0] = 1
    cl[y_pix,x_pix] = 0
    cl_dist, inds = ndimage.distance_transform_edt(cl, return_indices=True)
    dx,dy,dz,ds,s = compute_derivatives(x,y,z)
    # dx_pix,dy_pix,ds_pix,s_pix = compute_derivatives(x_pix,y_pix) # needed for s_pix only
    dx_pix = np.gradient(x_pix)
    dy_pix = np.gradient(y_pix)
    ds_pix = np.sqrt(dx_pix**2+dy_pix**2)
    s_pix = np.cumsum(ds_pix)
    f = scipy.interpolate.interp1d(s,z)
    snew = s_pix*s[-1]/s_pix[-1]
    if snew[-1]>s[-1]:
        snew[-1]=s[-1]
    snew[snew<s[0]]=s[0]
    z_pix = f(snew)
    # create along-channel distance map:
    z_map = np.zeros(np.shape(cl_dist)) 
    z_map[y_pix,x_pix]=z_pix
    xinds=inds[1,:,:]
    yinds=inds[0,:,:]
    for i in range(0,len(x_pix)):
        z_map[(xinds==x_pix[i]) & (yinds==y_pix[i])] = z_pix[i]
    return cl_dist, x_pix, y_pix, z_pix, s_pix, z_map, x, y, z

def erosion_surface(h,w,cl_dist,z):
    surf = z + (4*h/w**2)*(cl_dist+w*0.5)*(cl_dist-w*0.5)
    return surf

def point_bar_surface(surf,cl_dist,z,h,w):
    pb = z-h*np.exp(-(cl_dist**2)/(2*(w*0.33)**2))
    return pb

def sand_surface(surf,bth,dcr,cl_dist,z_map,h):
    relief = abs(surf-z_map+h)
    relief = abs(relief-np.amin(relief))
    th = bth * (1 - relief/dcr) # bed thickness inversely related to relief
    th[th<0] = 0.0
    return th, relief

def mud_surface(h_mud,levee_width,cl_dist,w,z_map,topo):
    surf1 = (-2*h_mud/levee_width)*cl_dist+h_mud;
    surf2 = (2*h_mud/levee_width)*cl_dist+h_mud;
    surf = np.minimum(surf1,surf2)
    surf3 = h_mud + (4*1.5*h_mud/w**2)*(cl_dist+w*0.5)*(cl_dist-w*0.5)
    surf = np.minimum(surf,surf3)
    surf[surf<0] = 0;
    relief = abs(topo-z_map)
    fth = 100.0
    th = 1 - relief/fth
    th[th<0] = 0
    th = surf * th
    return th

def topostrat(topo):
    r,c,ts = np.shape(topo)
    strat = np.copy(topo)
    for i in (range(0,ts)):
        strat[:,:,i] = np.amin(topo[:,:,i:], axis=2)
    return strat

def cl_dist_map(x,y,z,xmin,xmax,ymin,ymax,dx):
    # function for centerline rasterization and distance map calculation (does not return zmap!)
    y = y[(x>xmin) & (x<xmax)]
    z = z[(x>xmin) & (x<xmax)]
    x = x[(x>xmin) & (x<xmax)]    
    xdist = xmax - xmin
    ydist = ymax - ymin
    iwidth = int((xmax-xmin)/dx)
    iheight = int((ymax-ymin)/dx)
    xratio = iwidth/xdist
    # create list with pixel coordinates:
    pixels = []
    for i in range(0,len(x)):
        px = int(iwidth - (xmax - x[i]) * xratio)
        py = int(iheight - (ymax - y[i]) * xratio)
        pixels.append((px,py))
    # create image and numpy array:
    img = Image.new("RGB", (iwidth, iheight), "white")
    draw = ImageDraw.Draw(img)
    draw.line(pixels, fill="rgb(0, 0, 0)") # draw centerline as black line
    pix = np.array(img)
    cl = pix[:,:,0]
    cl[cl==255] = 1 # set background to 1 (centerline is 0)
    # calculate Euclidean distance map:
    cl_dist, inds = ndimage.distance_transform_edt(cl, return_indices=True)
    y_pix,x_pix = np.where(cl==0)
    return cl_dist, x_pix, y_pix

def eliminate_bad_pixels(img,img1):
    x_ind = np.where(img1==0)[1][0]
    y_ind = np.where(img1==0)[0][0]
    img[y_ind:y_ind+2,x_ind:x_ind+2] = np.ones(1,).astype(np.uint8)
    all_labels = measure.label(img,background=1,connectivity=2)
    cl=all_labels.copy()
    cl[cl==2]=0
    cl[cl>0]=1
    y_pix,x_pix = np.where(cl==1)
    return x_pix, y_pix

def order_cl_pixels(x_pix,y_pix):
    dist = distance.cdist(np.array([x_pix,y_pix]).T,np.array([x_pix,y_pix]).T)
    dist[np.diag_indices_from(dist)]=100.0
    ind = np.argmin(x_pix) # select starting point on left side of image
    clinds = [ind]
    count = 0
    while count<len(x_pix):
        t = dist[ind,:].copy()
        if len(clinds)>2:
            t[clinds[-2]]=t[clinds[-2]]+100.0
            t[clinds[-3]]=t[clinds[-3]]+100.0
        ind = np.argmin(t)
        clinds.append(ind)
        count=count+1
    x_pix = x_pix[clinds]
    y_pix = y_pix[clinds]
    return x_pix,y_pix

# functions for plotting results

def plot_surface(topo,ts,ci,ax,vmin,vmax,dx):
    # function for plotting contoured surface
    cax = ax.contourf(topo[:,:,ts*3+2].T,[i for i in range(vmin,vmax,5)],cmap=viridis,vmin=vmin,vmax=vmax)
    #plt.colorbar()
    ax.contour(topo[:,:,ts*3+2].T,[i for i in range(vmin,vmax,5)],colors='k',linestyles='solid',linewidth=0.5)
    ax.grid(b=None)
    ax.tick_params(axis='x',which='both',bottom='off',top='off',labelbottom='off')
    ax.tick_params(axis='y',which='both',left='off',right='off',labelleft='off')
    ax.plot([0,1000/dx],[-30,-30],linewidth=3,color='k')
    ax.text(300/dx,-39,'1 km')
    ax.set_ylim(ax.get_ylim()[::-1]) # invert y axis
    return cax

def create_random_section_2_points(ax,strat,x1,x2,y1,y2,s1,dx,ds):
    r, c, nt = np.shape(strat)
    dist = dx*((x2-x1)**2 + (y2-y1)**2)**0.5
    s2 = s1*dx+dist
    num = int(dist/float(ds))
    Xrand, Yrand, Srand = np.linspace(x1,x2,num), np.linspace(y1,y2,num), np.linspace(s1*dx,s2,num)
    for i in range(1,nt-2,4):
        strat_i = scipy.ndimage.map_coordinates(strat[:,:,i], np.vstack((Yrand,Xrand)))
        strat_ii = scipy.ndimage.map_coordinates(strat[:,:,i+1], np.vstack((Yrand,Xrand)))
        strat_iii = scipy.ndimage.map_coordinates(strat[:,:,i+2], np.vstack((Yrand,Xrand)))
        strat_iiii = scipy.ndimage.map_coordinates(strat[:,:,i+3], np.vstack((Yrand,Xrand)))
        X1 = np.concatenate((Srand, Srand[::-1]))  
        Y1 = np.concatenate((strat_i, strat_ii[::-1]))
        Y2 = np.concatenate((strat_ii, strat_iii[::-1]))
        Y3 = np.concatenate((strat_iii, strat_iiii[::-1])) 
        ax.fill(X1, Y1, facecolor=[0.5,0.25,0], linewidth=0.5)#, 'edgecolor', 'none') # oxbow
        ax.fill(X1, Y2, facecolor=[0.9,0.9,0], linewidth=0.5)#, 'edgecolor', 'none') # point bar
        ax.fill(X1, Y3, facecolor=[0.5,0.25,0], linewidth=0.5)#, 'edgecolor', 'none') # levee
        
def create_random_section_n_points(strat,x1,x2,y1,y2,dx,ds):
    fig = plt.figure()
    ax = fig.add_subplot(111)
    if type(x1)==int:
        create_random_section_2_points(ax,strat,x1,x2,y1,y2,dx,ds)
    else:
        dx1,dy1,ds1,s1 = compute_s_coord(x1,y1)
        for i in range(len(x1)):
            create_random_section_2_points(ax,strat,x1[i],x2[i],y1[i],y2[i],s1[i],dx,ds)
