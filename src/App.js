import React from 'react';
import Para4View from './Para4View.js';
import Vtk4View from './Vtk4View.js';
import SampleViewer from './SampleViewer.js'

import Toolbar from '@material-ui/core/Toolbar';
import Button from '@material-ui/core/Button'

export default class ReactApp extends React.Component
{
    constructor(props)
    {
        super(props);
        this.seriesUid = "1.3.12.2.1107.5.1.4.51964.4.0.3807800115682492";
    }

    render()
    {
      return <div className="App">
        <SampleViewer
        seriesUid={this.seriesUid}
        ></SampleViewer>
         </div>
    }
}
