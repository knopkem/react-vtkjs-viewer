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
import logging

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
        
            # draw the borders of a renderer's viewport
            def ViewportBorder(renderer, color, last):
                # points start at upper right and proceed anti-clockwise
                points = vtk.vtkPoints()
                points.SetNumberOfPoints(4)
                points.InsertPoint(0, 1, 1, 0)
                points.InsertPoint(1, 0, 1, 0)
                points.InsertPoint(2, 0, 0, 0)
                points.InsertPoint(3, 1, 0, 0)

                # create cells, and lines
                cells = vtk.vtkCellArray()
                cells.Initialize()

                lines = vtk.vtkPolyLine()

                # only draw last line if this is the last viewport
                # this prevents double vertical lines at right border
                # if different colors are used for each border, then do
                # not specify last
                if (last):
                    lines.GetPointIds().SetNumberOfIds(5)
                else:
                    lines.GetPointIds().SetNumberOfIds(4)

                for i in range(0,4):
                    lines.GetPointIds().SetId(i,i)
                
                if (last):
                    lines.GetPointIds().SetId(4, 0)

                cells.InsertNextCell(lines)

                # now make tge polydata and display it
                poly = vtk.vtkPolyData()
                poly.Initialize()
                poly.SetPoints(points)
                poly.SetLines(cells)

                # use normalized viewport coordinates since
                # they are independent of window size
                coordinate = vtk.vtkCoordinate()
                coordinate.SetCoordinateSystemToNormalizedViewport()

                mapper = vtk.vtkPolyDataMapper2D()
                mapper.SetInputData(poly)
                mapper.SetTransformCoordinate(coordinate)

                actor = vtk.vtkActor2D()
                actor.SetMapper(mapper)
                actor.GetProperty().SetColor(color)
                actor.GetProperty().SetLineWidth(2.0)

                renderer.AddViewProp(actor)
        
            def getViewport(viewNr):
                if viewNr == 0:
                    return [0.0, 0.5, 0.5, 1.0]
                elif viewNr == 1:
                    return [0.5, 0.5, 1.0, 1.0]
                elif viewNr == 2:
                    return [0.0, 0.0, 0.5, 0.5]
                elif viewNr == 3:
                    return [0.5, 0.0, 1.0, 0.5]
                else:
                    logging.warning('invalid view nr {}'.format(viewNr))
                    return [0.0, 0.0, 1.0, 1.0]

        
            def doVolumeRendering(renWin, reader, viewNr):
                # The volume will be displayed by ray-cast alpha compositing.
                # A ray-cast mapper is needed to do the ray-casting, and a
                # compositing function is needed to do the compositing along the ray.
                volumeMapper = vtk.vtkGPUVolumeRayCastMapper()
                volumeMapper.SetInputConnection(reader.GetOutputPort())
                volumeMapper.SetBlendModeToComposite()
                volumeMapper.AutoAdjustSampleDistancesOff()
                volumeMapper.UseJitteringOn()
                
                offset = -1024

                # The color transfer function maps voxel intensities to colors.
                # It is modality-specific, and often anatomy-specific as well.
                # The goal is to one color for flesh (between 500 and 1000)
                # and another color for bone (1150 and over).
                volumeColor = vtk.vtkColorTransferFunction()
                volumeColor.AddRGBPoint(1024 + offset, 0.53125, 0.171875, 0.0507813)
                volumeColor.AddRGBPoint(1031 + offset, 0.488281, 0.148438, 0.0351563)
                volumeColor.AddRGBPoint(1000 + offset, 0.589844, 0.0257813, 0.0148438)
                volumeColor.AddRGBPoint(1170 + offset, 0.589844, 0.0257813, 0.0148438)
                volumeColor.AddRGBPoint(1181 + offset, 0.957031, 0.996094, 0.878906)
                volumeColor.AddRGBPoint(2024 + offset, 0.976563, 0.996094, 0.929688)
                volumeColor.AddRGBPoint(3014 + offset, 0.488281, 0.488281, 0.488281)

                # The opacity transfer function is used to control the opacity
                # of different tissue types.
                volumeScalarOpacity = vtk.vtkPiecewiseFunction()
                #volumeScalarOpacity.AddPoint(0,    0.00)
                #volumeScalarOpacity.AddPoint(500,  0.15)
                #volumeScalarOpacity.AddPoint(1000, 0.15)
                #volumeScalarOpacity.AddPoint(1150, 0.85)

                volumeScalarOpacity.AddPoint(1131 + offset,  0)
                volumeScalarOpacity.AddPoint(1463 + offset,  1)
                volumeScalarOpacity.AddPoint(3135 + offset, 1)

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
                
                ren = vtk.vtkRenderer()
                ren.SetBackground(0.0, 0.0, 0.0)
                ren.SetViewport(*getViewport(viewNr))
                renWin.AddRenderer(ren)

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
                ViewportBorder(ren, [1,1,1], True)
                
                ren.ResetCamera();

            def doReslice(renWin, reader, viewNr, orientation, level, window):
                        
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
                if orientation == "coronal":
                    reslice.SetResliceAxes(coronal)
                if orientation == "sagittal":
                    reslice.SetResliceAxes(sagittal)
                reslice.SetInterpolationModeToLinear()

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
                
                cornerAnnotation = vtk.vtkCornerAnnotation()
                cornerAnnotation.SetLinearFontScaleFactor( 1 );
                cornerAnnotation.SetNonlinearFontScaleFactor( 1 );
                cornerAnnotation.SetMinimumFontSize( 12 );
                cornerAnnotation.SetMaximumFontSize( 20 );
                cornerAnnotation.SetText( 0, "lower left" );
                cornerAnnotation.SetText( 1, "lower right" );
                cornerAnnotation.SetText( 2, "upper left" );
                cornerAnnotation.SetText( 3, "upper right" );
                cornerAnnotation.GetTextProperty().SetColor( 1, 1, 1 );

                
                ren = vtk.vtkRenderer()
                ren.SetBackground(0.0, 0.0, 0.0)
                ren.AddActor(actor)
                #ren.AddViewProp( cornerAnnotation )
                ren.SetViewport(*getViewport(viewNr))
                renWin.AddRenderer(ren)
                ren.ResetCamera()
                
                
                
                camera = ren.GetActiveCamera()
                camera.Zoom(1.4)
                
                ViewportBorder(ren, [1,1,1], False)
                
                return reslice

            # Create the renderer, the render window, and the interactor. The renderer
            # draws into the render window, the interactor enables mouse- and
            # keyboard-based interaction with the scene.
           
            renWin = vtk.vtkRenderWindow()
            iren = vtk.vtkRenderWindowInteractor()
            iren.SetRenderWindow(renWin)
            interactorStyleImage = vtk.vtkInteractorStyleImage()
            interactorStyleTrackball = vtk.vtkInteractorStyleTrackballCamera()
            interactorStyleTrackball.SetMotionFactor(20) # 10 is default, we need twice the speed to compensate the smaller viewport
            iren.SetInteractorStyle(interactorStyleImage)

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

            meta = reader.GetMetaData();

            level = meta.Get(vtk.vtkDICOMTag(0x0028,0x1050)).AsUTF8String().split("\\")[0]
            window = meta.Get(vtk.vtkDICOMTag(0x0028,0x1051)).AsUTF8String().split("\\")[0]
            
            resliceList = []
            
            resliceList.append(doReslice(renWin, reader, 0, 'axial', level, window))

            resliceList.append(doReslice(renWin, reader, 1, 'coronal', level, window))

            resliceList.append(doReslice(renWin, reader, 2, 'sagittal', level, window))

            doVolumeRendering(renWin, reader, 3)

            # Create callbacks for slicing the image
            actions = {}
            actions["Slicing"] = 0
            actions["ViewNr"] = 0

            def GetViewNrOnMousePosition(iren):
                (mouseX, mouseY) = iren.GetEventPosition()
                (sizeX, sizeY) = iren.GetSize()
                ratioX = mouseX/sizeX
                ratioY = mouseY/sizeY
                if ( ratioX < 0.5 and ratioY < 0.5):
                    return 2
                elif ( ratioX > 0.5 and ratioY < 0.5):
                    return 3
                elif ( ratioX < 0.5 and ratioY > 0.5):
                    return 0
                else:
                    return 1

            def ButtonCallback(obj, event):
                actions["ViewNr"] = GetViewNrOnMousePosition(iren)
                if (actions["ViewNr"] >= 0 and actions["ViewNr"] <= 2):
                    iren.SetInteractorStyle(interactorStyleImage)
                else:
                    iren.SetInteractorStyle(interactorStyleTrackball)

                if event == "LeftButtonPressEvent":
                    actions["Slicing"] = 1
                    iren.GetInteractorStyle().OnLeftButtonDown()
                else:
                    actions["Slicing"] = 0
                    iren.GetInteractorStyle().OnLeftButtonUp()


            def MouseMoveCallback(obj, event):
                (lastX, lastY) = iren.GetLastEventPosition()
                (mouseX, mouseY) = iren.GetEventPosition()
                if actions["Slicing"] == 1 and actions["ViewNr"] >= 0 and actions["ViewNr"] <= 2:
                    deltaY = mouseY - lastY
                    reslice = resliceList[actions["ViewNr"]]
                    reslice.Update()
                    sliceSpacing = reslice.GetOutput().GetSpacing()[2]
                    matrix = reslice.GetResliceAxes()
                    # move the center point that we are slicing through
                    center = matrix.MultiplyPoint((0, 0, sliceSpacing*deltaY, 1))
                    matrix.SetElement(0, 3, center[0])
                    matrix.SetElement(1, 3, center[1])
                    matrix.SetElement(2, 3, center[2])
                    renWin.Render()
                else:
                    currentViewNr = GetViewNrOnMousePosition(iren)
                    if (currentViewNr == 3):
                        iren.GetInteractorStyle().OnMouseMove()

            interactorStyleTrackball.AddObserver("MouseMoveEvent", MouseMoveCallback)
            interactorStyleTrackball.AddObserver("LeftButtonPressEvent", ButtonCallback)
            interactorStyleTrackball.AddObserver("LeftButtonReleaseEvent", ButtonCallback)
            
            interactorStyleImage.AddObserver("MouseMoveEvent", MouseMoveCallback)
            interactorStyleImage.AddObserver("LeftButtonPressEvent", ButtonCallback)
            interactorStyleImage.AddObserver("LeftButtonReleaseEvent", ButtonCallback)

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
