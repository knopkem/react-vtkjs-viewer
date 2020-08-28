import React from 'react';
import StreamViewer from './StreamViewer.js';
import VTKLoadImageDataExample from './VTKLoadImageDataExample.js';
import VTKMPRRotateExample from './VTKMPRRotateExample.js';
import VTKVolumeRenderingExample from './VTKVolumeRenderingExample.js';

import Toolbar from '@material-ui/core/Toolbar';
import Button from '@material-ui/core/Button'
import Grid from '@material-ui/core/Grid';

export default class ReactApp extends React.Component
{
    constructor(props)
    {
        super(props);
        this.gridContainter = 
        {
          display: 'grid',
          gridTemplateColumns: '400px 400px',
          gridTemplateRows: '400px 400px',
        };
    }

    render()
    {
      return <div className="App">
          <Grid container>
          <Grid container item>
            <Grid item style={{width: "50%", height: "50%"}}>
              <StreamViewer
                sliceOrientation='axial'
                type='mpr'
                id='1'
              ></StreamViewer>
            </Grid>
            <Grid item style={{width: "50%", height: "50%"}}>
              <StreamViewer
                sliceOrientation='sagittal'
                type='mpr'
                id='2'
              ></StreamViewer>
            </Grid>
          </Grid>
          <Grid container item>
            <Grid item style={{width: "50%", height: "50%"}}>
              <StreamViewer
              sliceOrientation='coronal'
              type='mpr'
              id='3'
              ></StreamViewer>
            </Grid>
            <Grid item style={{width: "50%", height: "50%"}}>
              <StreamViewer
              sliceOrientation='axial'
              type='vrt'
              id='4'
              ></StreamViewer>
            </Grid>
          </Grid>
        </Grid>
         </div>
    }
  }
