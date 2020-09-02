import React from 'react';
import ParaStreamViewer from './ParaStreamViewer.js';

import Grid from '@material-ui/core/Grid';

export default class Para4View extends React.Component
{
    constructor(props)
    {
        super(props);
        this.seriesUid = props.seriesUid;
    }

    render()
    {
      const style = {
        width: '50%',
        height: '50%',
      }

      return <Grid container>
          <Grid container item>
            <Grid item style={style}>
              <ParaStreamViewer
                sliceOrientation='axial'
                type='mpr'
                viewid='1'
                seriesUid={this.seriesUid}
              ></ParaStreamViewer>
            </Grid>
            <Grid item style={{style}}>
              <ParaStreamViewer
                sliceOrientation='sagittal'
                type='mpr'
                viewid='2'
                seriesUid={this.seriesUid}
              ></ParaStreamViewer>
            </Grid>
          </Grid>
          <Grid container item>
            <Grid item style={{style}}>
              <ParaStreamViewer
              sliceOrientation='coronal'
              type='mpr'
              viewid='3'
              seriesUid={this.seriesUid}
              ></ParaStreamViewer>
            </Grid>
            <Grid item style={{style}}>
              <ParaStreamViewer
              sliceOrientation='axial'
              type='vrt'
              viewid='4'
              seriesUid={this.seriesUid}
              ></ParaStreamViewer>
            </Grid>
          </Grid>
        </Grid>
    }
  }
