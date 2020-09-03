r"""
    This module is a ParaViewWeb server application.
    The following command line illustrates how to use it::

        $ vtkpython .../server.py

    Any ParaViewWeb executable script comes with a set of standard arguments that can be overrides if need be::

        --port 8080
            Port number on which the HTTP server will listen.

        --content /path-to-web-content/
            Directory that you want to serve as static web content.
            By default, this variable is empty which means that we rely on another
            server to deliver the static content and the current process only
            focuses on the WebSocket connectivity of clients.

        --authKey vtkweb-secret
            Secret key that should be provided by the client to allow it to make
            any WebSocket communication. The client will assume if none is given
            that the server expects "vtkweb-secret" as secret key.

"""
import os
import sys
import argparse

# Try handle virtual env if provided
if '--virtual-env' in sys.argv:
  virtualEnvPath = sys.argv[sys.argv.index('--virtual-env') + 1]
  virtualEnv = virtualEnvPath + '/bin/activate_this.py'
  if 'execfile' in dir():
    execfile(virtualEnv, dict(__file__=virtualEnv))
  else:
    exec(open(virtualEnv).read(), dict(__file__=virtualEnv))

# from __future__ import absolute_import, division, print_function

from wslink import server
from wslink import register as exportRpc

from vtk.web import wslink as vtk_wslink
from vtk.web import protocols as vtk_protocols

import vtk
import vtk_override_protocols
from vtk_protocol import VtkCone
import mysql.connector
from credentials import credentials

# =============================================================================
# Server class
# =============================================================================

class _Server(vtk_wslink.ServerProtocol):
    # Defaults
    authKey = "wslink-secret"
    view = None

    @staticmethod
    def add_arguments(parser):
        parser.add_argument("--virtual-env", default=None,
                            help="Path to virtual environment to use")

    @staticmethod
    def configure(args):
        # Standard args
        _Server.authKey = args.authKey

    def initialize(self):
    
        # Bring used components
        self.registerVtkWebProtocol(vtk_protocols.vtkWebMouseHandler())
        self.registerVtkWebProtocol(vtk_protocols.vtkWebViewPort())
        self.registerVtkWebProtocol(vtk_override_protocols.vtkWebPublishImageDelivery(decode=False))

        # Custom API
        self.registerVtkWebProtocol(VtkCone())

        # tell the C++ web app to use no encoding.
        # ParaViewWebPublishImageDelivery must be set to decode=False to match.
        self.getApplication().SetImageEncoding(0)

        # Update authentication key to use
        self.updateSecret(_Server.authKey)

        if not _Server.view:

            # Create the renderer, the render window, and the interactor. The renderer
            # draws into the render window, the interactor enables mouse- and
            # keyboard-based interaction with the scene.
            ren = vtk.vtkRenderer()
            renWin = vtk.vtkRenderWindow()
            renWin.AddRenderer(ren)
            iren = vtk.vtkRenderWindowInteractor()
            iren.SetRenderWindow(renWin)
            iren.GetInteractorStyle().SetCurrentStyleToTrackballCamera()

            cred = credentials()

            mydb = mysql.connector.connect(
              host="localhost",
              user=cred[0],
              password=cred[1],
              database="iqweb"
            )

            mycursor = mydb.cursor()
            sql = "SELECT path FROM image WHERE seriesuid = %s"
            params = (self.uid,)
            mycursor.execute(sql, params)

            files = mycursor.fetchall()
            fileset = vtk.vtkStringArray()
            for file in files:
                fileset.InsertNextValue(file[0])

            sorter = vtk.vtkDICOMFileSorter()
            sorter.SetInputFileNames(fileset)
            sorter.Update()

            sortedFiles = vtk.vtkStringArray()
            sortedFiles = sorter.GetFileNamesForSeries(0)

            reader = vtk.vtkDICOMReader()
            reader.AutoRescaleOff() #only because our preset is shifted
            reader.SetFileNames(sortedFiles);
            reader.Update()

            # The volume will be displayed by ray-cast alpha compositing.
            # A ray-cast mapper is needed to do the ray-casting, and a
            # compositing function is needed to do the compositing along the ray.
            volumeMapper = vtk.vtkGPUVolumeRayCastMapper()
            volumeMapper.SetInputConnection(reader.GetOutputPort())
            volumeMapper.SetBlendModeToComposite()
            volumeMapper.AutoAdjustSampleDistancesOff()
            volumeMapper.UseJitteringOn()

            # The color transfer function maps voxel intensities to colors.
            # It is modality-specific, and often anatomy-specific as well.
            # The goal is to one color for flesh (between 500 and 1000)
            # and another color for bone (1150 and over).
            volumeColor = vtk.vtkColorTransferFunction()
            volumeColor.AddRGBPoint(1024, 0.53125, 0.171875, 0.0507813)
            volumeColor.AddRGBPoint(1031, 0.488281, 0.148438, 0.0351563)
            volumeColor.AddRGBPoint(1000, 0.589844, 0.0257813, 0.0148438)
            volumeColor.AddRGBPoint(1170, 0.589844, 0.0257813, 0.0148438)
            volumeColor.AddRGBPoint(1181, 0.957031, 0.996094, 0.878906)
            volumeColor.AddRGBPoint(2024, 0.976563, 0.996094, 0.929688)
            volumeColor.AddRGBPoint(3014, 0.488281, 0.488281, 0.488281)

            # The opacity transfer function is used to control the opacity
            # of different tissue types.
            volumeScalarOpacity = vtk.vtkPiecewiseFunction()
            #volumeScalarOpacity.AddPoint(0,    0.00)
            #volumeScalarOpacity.AddPoint(500,  0.15)
            #volumeScalarOpacity.AddPoint(1000, 0.15)
            #volumeScalarOpacity.AddPoint(1150, 0.85)

            volumeScalarOpacity.AddPoint(1131,  0)
            volumeScalarOpacity.AddPoint(1463,  1)
            volumeScalarOpacity.AddPoint(3135, 1)

            # The gradient opacity function is used to decrease the opacity
            # in the "flat" regions of the volume while maintaining the opacity
            # at the boundaries between tissue types.  The gradient is measured
            # as the amount by which the intensity changes over unit distance.
            # For most medical data, the unit distance is 1mm.
            volumeGradientOpacity = vtk.vtkPiecewiseFunction()
            volumeGradientOpacity.AddPoint(0,   0.0)
            volumeGradientOpacity.AddPoint(90,  0.9)
            volumeGradientOpacity.AddPoint(100, 1.0)

            # The VolumeProperty attaches the color and opacity functions to the
            # volume, and sets other volume properties.  The interpolation should
            # be set to linear to do a high-quality rendering.  The ShadeOn option
            # turns on directional lighting, which will usually enhance the
            # appearance of the volume and make it look more "3D".  However,
            # the quality of the shading depends on how accurately the gradient
            # of the volume can be calculated, and for noisy data the gradient
            # estimation will be very poor.  The impact of the shading can be
            # decreased by increasing the Ambient coefficient while decreasing
            # the Diffuse and Specular coefficient.  To increase the impact
            # of shading, decrease the Ambient and increase the Diffuse and Specular.
            volumeProperty = vtk.vtkVolumeProperty()
            volumeProperty.SetColor(volumeColor)
            volumeProperty.SetScalarOpacity(volumeScalarOpacity)
            volumeProperty.SetGradientOpacity(volumeGradientOpacity)
            volumeProperty.SetInterpolationTypeToLinear()
            volumeProperty.ShadeOn()
            volumeProperty.SetAmbient(0.4) # 0.1
            volumeProperty.SetDiffuse(0.5) # 0.9
            volumeProperty.SetSpecular(0.2) # 0.2
            volumeProperty.SetSpecularPower(10)

            # The vtkVolume is a vtkProp3D (like a vtkActor) and controls the position
            # and orientation of the volume in world coordinates.
            volume = vtk.vtkVolume()
            volume.SetMapper(volumeMapper)
            volume.SetProperty(volumeProperty)

            # Finally, add the volume to the renderer
            ren.AddViewProp(volume)

            # Set up an initial view of the volume.  The focal point will be the
            # center of the volume, and the camera position will be 400mm to the
            # patient's left (which is our right).
            camera =  ren.GetActiveCamera()
            c = volume.GetCenter()
            camera.SetFocalPoint(c[0], c[1], c[2])
            camera.SetPosition(c[0] + 400, c[1], c[2])
            camera.SetViewUp(0, 0, -1)
            
            ren.ResetCamera();

            # Increase the size of the render window
            #renWin.SetSize(640, 480)
            #renWin.SetSize(432, 336)
            renWin.SetSize(320,240)

            # Interact with the data.
            #iren.Initialize()
            renWin.Render()
            #iren.Start()
                        
            
            # vtkweb
            self.getApplication().GetObjectIdMap().SetActiveObject("VIEW", renWin)

# =============================================================================
# Main: Parse args and start serverviewId
# =============================================================================

if __name__ == "__main__":
    # Create argument parser
    parser = argparse.ArgumentParser(description="Cone example")

    # Add arguments
    server.add_arguments(parser)
    _Server.add_arguments(parser)
    args = parser.parse_args()
    _Server.configure(args)

    # Start server
    server.start_webserver(options=args, protocol=_Server, disableLogging=True)
