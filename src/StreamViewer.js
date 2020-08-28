// react 
import React from 'react'
// vtk
import vtkWSLinkClient from "vtk.js/Sources/IO/Core/WSLinkClient";
import SmartConnect from "wslink/src/SmartConnect";
import vtkRemoteView from "vtk.js/Sources/Rendering/Misc/RemoteView";
import { connectImageStream } from "vtk.js/Sources/Rendering/Misc/RemoteView";
import {default as UUID} from "node-uuid";

export default class StreamViewer extends React.Component
{
  constructor(props)
  {
    super(props);
    this.view= vtkRemoteView.newInstance({
        rpcWheelEvent: "viewport.mouse.zoom.wheel",
      });
    vtkWSLinkClient.setSmartConnectClass(SmartConnect);
    this.clientToConnect = vtkWSLinkClient.newInstance();
    this.id = UUID.v4();
  }

  shouldComponentUpdate(nextProps, nextState)
  {
    if(!super.shouldComponentUpdate(nextProps, nextState))
    {
      return false;
    }
    return true;
  }

  componentDidMount()
  {
    const renderDiv = document.getElementById(this.id);

    renderDiv.style.position = "relative";
    renderDiv.style.width = "50vw";
    renderDiv.style.height = "50vh";
    renderDiv.style.overflow = "hidden";

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
      });

      // Close
    this.clientToConnect.onConnectionClose((httpReq) => {
        const message =
        (httpReq && httpReq.response && httpReq.response.error) ||
        `Connection close`;
        console.error(message);
        console.log(httpReq);
      });
  
    const config = {
        application: this.props.type, 
        uid: "1.3.12.2.1107.5.1.4.51964.4.0.3807800115682492", 
        orientation: this.props.sliceOrientation,
    };


    // Connect
    this.clientToConnect
        .connect(config)
        .then((validClient) => {
        connectImageStream(validClient.getConnection().getSession());
    
        const session = validClient.getConnection().getSession();
        this.view.setSession(session);
        this.view.setViewId(parseInt(this.props.id));
        this.view.render();
        })
        .catch((error) => {
            console.error(error);
        });
  }

  render()
  {
    this.view.render();
    return <div id={this.id} />;
  }
}