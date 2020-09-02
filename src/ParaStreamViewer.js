// react 
import React from 'react'

import SmartConnect from "wslink/src/SmartConnect";
import {default as UUID} from "node-uuid";

// paraview
import RemoteRenderer from 'paraviewweb/src/NativeUI/Canvas/RemoteRenderer';
import SizeHelper from 'paraviewweb/src/Common/Misc/SizeHelper';
import ParaViewWebClient from 'paraviewweb/src/IO/WebSocket/ParaViewWebClient';

// vtk
import vtkWSLinkClient from "vtk.js/Sources/IO/Core/WSLinkClient";

export default class ParaStreamViewer extends React.Component
{
  constructor(props)
  {
    super(props);
    vtkWSLinkClient.setSmartConnectClass(SmartConnect);
    this.clientToConnect = vtkWSLinkClient.newInstance();
    this.id = UUID.v4();
    this.loaderId = 'loader_' + this.id;
    this.loaderStyle = {
      color: 'white',
    };
    this.canvasStyle = {
      position: 'relative',
      width: '50vw',
      height: '50vh',
      overflow: 'hidden',
      outline: '1px solid white',
      background: 'black'
    }
    this.state = {
      message: 'Loading...',
    }
  }

  componentDidMount()
  {
    const renderDiv = document.getElementById(this.id);

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
        application: this.props.type, 
        uid: this.props.seriesUid, 
        orientation: this.props.sliceOrientation
    };


    // Connect
    console.log('connecting to remote...');
    this.clientToConnect
        .connect(config)
        .then((validClient) => {
          console.log('connected');

          const connection = validClient.getConnection();
          const pvwClient = ParaViewWebClient.createClient(connection, [
            'MouseHandler',
            'ViewPort',
            'ViewPortImageDelivery',
          ]);
          const renderer = new RemoteRenderer(pvwClient);
          renderer.setContainer(renderDiv);
          renderer.onImageReady(() => {
            console.log('Image ready');
            const loaderDiv = document.getElementById(this.loaderId);
            if (loaderDiv) {
              renderDiv.removeChild(loaderDiv);
            }
          });
          window.renderer = renderer;
          SizeHelper.onSizeChange(() => {
            renderer.resize();
          });
          SizeHelper.startListening();
        })
        .catch((error) => {
            console.error(error);
        });
  }

  render()
  { 
    return <div id={this.id} style= {this.canvasStyle}><div id={this.loaderId} style={this.loaderStyle} >{this.state.message}</div></div>;
  }
}