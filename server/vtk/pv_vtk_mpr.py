r"""
    This module is a VTK Web server application.
    The following command line illustrates how to use it::

        $ vtkpython .../vtk_server.py

    Any VTK Web executable script comes with a set of standard arguments that
    can be overriden if need be::
        --host localhost
             Interface on which the HTTP server will listen.

        --port 8080
             Port number on which the HTTP server will listen.

        --content /path-to-web-content/
             Directory that you want to serve as static web content.
             By default, this variable is empty which means that we rely on another server
             to deliver the static content and the current process only focuses on the
             WebSocket connectivity of clients.

        --authKey wslink-secret
             Secret key that should be provided by the client to allow it to make any
             WebSocket communication. The client will assume if none is given that the
             server expects "wslink-secret" as the secret key.
"""

# import to process args
import sys
import os

import mysql.connector
from credentials import credentials

# import vtk modules.
import vtk
from vtk.web import protocols
from vtk.web import wslink as vtk_wslink
from wslink import server

try:
    import argparse
except ImportError:
    # since  Python 2.6 and earlier don't have argparse, we simply provide
    # the source for the same as _argparse and we use it instead.
    from vtk.util import _argparse as argparse

# =============================================================================
# Create custom ServerProtocol class to handle clients requests
# =============================================================================

class _WebCone(vtk_wslink.ServerProtocol):

    # Application configuration
    view    = None
    authKey = "wslink-secret"
    uid = ""
    orientation = "axial"


    def initialize(self):
        global renderer, renderWindow, renderWindowInteractor, cone, mapper, actor

        # Bring used components
        self.registerVtkWebProtocol(protocols.vtkWebMouseHandler())
        self.registerVtkWebProtocol(protocols.vtkWebViewPort())
        self.registerVtkWebProtocol(protocols.vtkWebViewPortImageDelivery())
        self.registerVtkWebProtocol(protocols.vtkWebViewPortGeometryDelivery())

        # Update authentication key to use
        self.updateSecret(_WebCone.authKey)

        # Create default pipeline (Only once for all the session)
        if not _WebCone.view:

            def GetDiagonalFromBounds(bounds):
                box = vtk.vtkBoundingBox(bounds)
                box.SetBounds(bounds)
                distance = box.GetDiagonalLength()
                return distance
                
            def setupCamera( renWin, ren, width, height ):
                print("setting up camera")
                renWin.SetSize( width, height )
                camera = ren.GetActiveCamera()
                cameraDistance = 10
                sliceHalfThickness = 1
                xFocal = ( width - 1 ) / 2.0
                yFocal = ( height - 1 ) / 2.0
                #camera.SetFocalPoint( xFocal, yFocal, 0.0 )
                camera.SetPosition( xFocal, yFocal, cameraDistance )
                camera.SetViewUp( 0, 1, 0 )
                camera.SetClippingRange( cameraDistance - sliceHalfThickness, cameraDistance + sliceHalfThickness )
                #camera.SetParallelScale( ( height - 1 ) / 2.0 )
                camera.ParallelProjectionOn()

            try:
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
                
                origin = [x0, y0, z0]
                spacing = [xSpacing, ySpacing, zSpacing]
                extent = [xMin, xMax, yMin, yMax, zMin, zMax]
                bounds = [ extent[0]/spacing[0], extent[1]/spacing[0], extent[2]/spacing[1], extent[3]/spacing[1], extent[4]/spacing[2], extent[5]/spacing[2] ] 
                diagonal = GetDiagonalFromBounds(bounds)
                originOut = [diagonal * spacing[0]/2, -diagonal * spacing[1]/2]


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
                #reslice.SetOutputOrigin(origin)
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

        
                xc = origin[0] + 0.5*(extent[0] + extent[1])*spacing[0]
                yc = origin[1] + 0.5*(extent[2] + extent[3])*spacing[1]
                xd = (extent[1] - extent[0] + 1)*spacing[0]
                yd = (extent[3] - extent[2] + 1)*spacing[1]
                
                
               
                ren.ResetCamera()
                camera = ren.GetActiveCamera()
                camera.Zoom(1.4)
                #d = camera.GetDistance()
                #camera.SetParallelScale(0.5 * yd)
                #camera.SetFocalPoint(xc, yc, 0.0)
                #camera.SetPosition(xc, yc, d)
                
                #setupCamera(renWin, ren, 320, 240)
                renWin.Render()
                
                # vtkweb
                self.getApplication().GetObjectIdMap().SetActiveObject("VIEW", renWin)
            except:
                print("Unexpected error:", sys.exc_info()[0])
                exit()

# =============================================================================
# Main: Parse args and start server
# =============================================================================

if __name__ == "__main__":
    # Create argument parser
    parser = argparse.ArgumentParser(description="VTK/Web Cone web-application")

    # Add default arguments
    server.add_arguments(parser)

    # Extract arguments
    args = parser.parse_args()

    # Configure our current application
    _WebCone.authKey = args.authKey
    
    _WebCone.uid = args.content
    _WebCone.orientation = args.uploadPath

    # Start server
    server.start_webserver(options=args, protocol=_WebCone)