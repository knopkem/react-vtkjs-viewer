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
    uid = ""
    orientation = "axial"
    view = None

    @staticmethod
    def add_arguments(parser):
        parser.add_argument("--virtual-env", default=None,
                            help="Path to virtual environment to use")

    @staticmethod
    def configure(args):
        # Standard args
        _Server.authKey = args.authKey
        _Server.uid = args.content
        _Server.orientation = args.uploadPath

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
            interactorStyle = vtk.vtkInteractorStyleImage()
            iren.SetInteractorStyle(interactorStyle)
            
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
            reader.SetFileNames(sortedFiles);
            reader.Update()

            # Calculate the center of the volume
            reader.Update()
            (xMin, xMax, yMin, yMax, zMin, zMax) = reader.GetExecutive().GetWholeExtent(reader.GetOutputInformation(0))
            (xSpacing, ySpacing, zSpacing) = reader.GetOutput().GetSpacing()
            (x0, y0, z0) = reader.GetOutput().GetOrigin()

            center = [x0 + xSpacing * 0.5 * (xMin + xMax),
                      y0 + ySpacing * 0.5 * (yMin + yMax),
                      z0 + zSpacing * 0.5 * (zMin + zMax)]

            # Matrices for axial, coronal, sagittal, oblique view orientations
            axial = vtk.vtkMatrix4x4()
            axial.DeepCopy((1, 0, 0, center[0],
                            0, 1, 0, center[1],
                            0, 0, 1, center[2],
                            0, 0, 0, 1))

            coronal = vtk.vtkMatrix4x4()
            coronal.DeepCopy((1, 0, 0, center[0],
                              0, 0, 1, center[1],
                              0,-1, 0, center[2],
                              0, 0, 0, 1))

            sagittal = vtk.vtkMatrix4x4()
            sagittal.DeepCopy((0, 0,-1, center[0],
                               1, 0, 0, center[1],
                               0,-1, 0, center[2],
                               0, 0, 0, 1))

            # Extract a slice in the desired orientation
            reslice = vtk.vtkImageReslice()
            reslice.SetInputConnection(reader.GetOutputPort())
            reslice.SetOutputDimensionality(2)
            reslice.SetResliceAxes(axial)
            if self.orientation == "coronal":
                reslice.SetResliceAxes(coronal)
            if self.orientation == "sagittal":
                reslice.SetResliceAxes(sagittal)
            reslice.SetInterpolationModeToLinear()

            meta = reader.GetMetaData();

            level = meta.Get(vtk.vtkDICOMTag(0x0028,0x1050)).AsUTF8String().split("\\")[0]
            window = meta.Get(vtk.vtkDICOMTag(0x0028,0x1051)).AsUTF8String().split("\\")[0]

            range1 = int(level) - int(window)/2
            range2 = int(level) + int(window)/2

            # Create a greyscale lookup table
            table = vtk.vtkLookupTable()
            table.SetRange(range1, range2) # image intensity range
            table.SetValueRange(0.0, 1.0) # from black to white
            table.SetSaturationRange(0.0, 0.0) # no color saturation
            table.SetRampToLinear()
            table.Build()

            # Map the image through the lookup table
            color = vtk.vtkImageMapToColors()
            color.SetLookupTable(table)
            color.SetInputConnection(reslice.GetOutputPort())

            # Display the image
            actor = vtk.vtkImageActor()
            actor.GetMapper().SetInputConnection(color.GetOutputPort())

            ren.AddActor(actor)


            # Create callbacks for slicing the image
            actions = {}
            actions["Slicing"] = 0

            def ButtonCallback(obj, event):
                if event == "LeftButtonPressEvent":
                    actions["Slicing"] = 1
                else:
                    actions["Slicing"] = 0

            def MouseMoveCallback(obj, event):
                (lastX, lastY) = iren.GetLastEventPosition()
                (mouseX, mouseY) = iren.GetEventPosition()
                if actions["Slicing"] == 1:
                    deltaY = mouseY - lastY
                    reslice.Update()
                    sliceSpacing = reslice.GetOutput().GetSpacing()[2]
                    matrix = reslice.GetResliceAxes()
                    # move the center point that we are slicing through
                    center = matrix.MultiplyPoint((0, 0, sliceSpacing*deltaY, 1))
                    matrix.SetElement(0, 3, center[0])
                    matrix.SetElement(1, 3, center[1])
                    matrix.SetElement(2, 3, center[2])
                    window.Render()
                else:
                    interactorStyle.OnMouseMove()


            interactorStyle.AddObserver("MouseMoveEvent", MouseMoveCallback)
            interactorStyle.AddObserver("LeftButtonPressEvent", ButtonCallback)
            interactorStyle.AddObserver("LeftButtonReleaseEvent", ButtonCallback)

            renWin.Render()
            
            # vtkweb
            self.getApplication().GetObjectIdMap().SetActiveObject("VIEW", renWin)

# =============================================================================
# Main: Parse args and start serverviewId
# =============================================================================

if __name__ == "__main__":
    # Create argument parser
    parser = argparse.ArgumentParser(description="MPR")

    # Add arguments
    server.add_arguments(parser)
    _Server.add_arguments(parser)
    args = parser.parse_args()
    _Server.configure(args)

    # Start server
    server.start_webserver(options=args, protocol=_Server, disableLogging=True)
