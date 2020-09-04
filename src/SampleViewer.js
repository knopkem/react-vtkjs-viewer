// react 
import React from 'react'

import SmartConnect from "wslink/src/SmartConnect";
import {default as UUID} from "node-uuid";
import coneProtocol from './protocol.js';

// vtk
import vtkWSLinkClient from "vtk.js/Sources/IO/Core/WSLinkClient";
import vtkRemoteView from "vtk.js/Sources/Rendering/Misc/RemoteView";
import { connectImageStream } from "vtk.js/Sources/Rendering/Misc/RemoteView";
import Slider from '@material-ui/core/Slider';

export default class SampleViewer extends React.Component
{
  constructor(props)
  {
    super(props);
    this.view = vtkRemoteView.newInstance({
        rpcWheelEvent: "viewport.mouse.zoom.wheel",
      });
    vtkWSLinkClient.setSmartConnectClass(SmartConnect);
    this.clientToConnect = vtkWSLinkClient.newInstance();
    this.clientToConnect.setProtocols({
      Cone: coneProtocol,
    });
    this.id = UUID.v4();
    this.loaderId = 'loader_' + this.id;

    this.loaderStyle = {
      color: 'white',
    };
    this.canvasStyle = {
      position: 'relative',
      width: '100vw',
      height: '100vh',
      overflow: 'hidden',
      background: 'black',
    }
    this.state = {
      message: 'Loading...',
      sliderValue: 30,
    }
    this.handleChange = (event, newValue) => {
      if (this.validClient) {
        this.validClient.getRemote()
        .Cone.updateResolution(newValue)
        .then(result => {
          console.log('resolution updated', result);
        });
      }
      this.setState({sliderValue: newValue});
    };
    this.validClient = null;
  }


  componentDidMount()
  {
    const renderDiv = document.getElementById(this.id);

    this.view.setContainer(renderDiv);
    this.view.setInteractiveRatio(0.7);
    this.view.setInteractiveQuality(15);

    window.addEventListener('resize', this.view.resize);


    // Error
    this.clientToConnect.onConnectionError((httpReq) => {
        const message =
          (httpReq && httpReq.response && httpReq.response.error) ||
          `Connection error`;
        console.error(message);
        console.log(httpReq);
        this.setState({ message });
      });

      // Close
    this.clientToConnect.onConnectionClose((httpReq) => {
        const message =
        (httpReq && httpReq.response && httpReq.response.error) ||
        `Connection close`;
        console.error(message);
        console.log(httpReq);
        this.setState({ message });
      });
  
    const config = {
        application: 'cone',
        sessionURL: 'ws://localhost:9999/ws'
    };


    // Connect
    console.log('connecting to remote...');
    this.clientToConnect
        .connect(config)
        .then((validClient) => {
          console.log('connected');
          const session = validClient.getConnection().getSession();
          connectImageStream(session);
          this.view.setSession(session);
          this.view.setViewId(-1);
          this.view.render();
          const loaderDiv = document.getElementById(this.loaderId);
          if (loaderDiv) {
            renderDiv.removeChild(loaderDiv);
            renderDiv.style.background = '';
          }
          validClient.getRemote()
          .Cone.createVisualization()
          .then(
            ({ focalPoint, viewUp, position, centerOfRotation, bounds }) => {
              console.log({
                focalPoint,
                viewUp,
                position,
                centerOfRotation,
                bounds,
              });
            }
          );
         this.validClient = validClient;
        })
        .catch((error) => {
            console.error(error);
        });
  }


  render()
  {
 
    return     <div>
    <Slider value={this.state.sliderValue} onChange={this.handleChange} aria-labelledby="continuous-slider" />
    <div id={this.id} style= {this.canvasStyle}>
    <div id={this.loaderId} style={this.loaderStyle} >{this.state.message}</div>
    </div>;
    </div>
  }
}