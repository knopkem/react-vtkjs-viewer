import React from 'react';
import StreamViewer from './StreamViewer.js';

export default class Vtk4View extends React.Component
{
    constructor(props)
    {
        super(props);
        this.seriesUid = props.seriesUid;
    }

    render()
    {
      return <StreamViewer
            type='4view'
            viewid='1'
            seriesUid={this.seriesUid}
        ></StreamViewer>
    }
  }
