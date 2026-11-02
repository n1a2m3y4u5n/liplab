param(
    [Parameter(Mandatory=$true)][string]$InputCsv,
    [Parameter(Mandatory=$true)][string]$OutputPng
)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $OutputPng){throw 'Refuse to overwrite plot'}
Add-Type -AssemblyName System.Windows.Forms.DataVisualization
Add-Type -AssemblyName System.Drawing
$rows=@(Import-Csv -LiteralPath $InputCsv)
if($rows.Count -ne 3){throw 'Expected three fixed capacity points'}
$chart=New-Object System.Windows.Forms.DataVisualization.Charting.Chart
try {
    $chart.Width=1200; $chart.Height=700
    $chart.BackColor=[Drawing.Color]::White
    $chart.Font=New-Object Drawing.Font('Arial',12)
    $area=New-Object System.Windows.Forms.DataVisualization.Charting.ChartArea('Capacity')
    $area.AxisX.Title='Student parameters / fixed teacher (%)'
    $area.AxisY.Title='Validation accuracy difference (percentage points)'
    $area.AxisX.Minimum=0; $area.AxisX.Maximum=45; $area.AxisX.Interval=5
    $ys=@($rows | ForEach-Object {[double]$_.accuracy_delta_pp})
    $area.AxisY.Minimum=[Math]::Min(-4,[Math]::Floor(($ys | Measure-Object -Minimum).Minimum)-1)
    $area.AxisY.Maximum=[Math]::Max(2,[Math]::Ceiling(($ys | Measure-Object -Maximum).Maximum)+1)
    $area.AxisX.MajorGrid.LineColor=[Drawing.Color]::Gainsboro
    $area.AxisY.MajorGrid.LineColor=[Drawing.Color]::Gainsboro
    $area.AxisX.LabelStyle.Format='0'
    $area.AxisY.LabelStyle.Format='0.0'
    $chart.ChartAreas.Add($area)
    $legend=New-Object System.Windows.Forms.DataVisualization.Charting.Legend('Legend')
    $legend.Docking=[System.Windows.Forms.DataVisualization.Charting.Docking]::Bottom
    $chart.Legends.Add($legend)
    $line=New-Object System.Windows.Forms.DataVisualization.Charting.Series('Fixed capacities (descriptive connection)')
    $line.ChartType=[System.Windows.Forms.DataVisualization.Charting.SeriesChartType]::Line
    $line.BorderWidth=2; $line.Color=[Drawing.Color]::SlateGray
    $line.MarkerStyle=[System.Windows.Forms.DataVisualization.Charting.MarkerStyle]::Circle
    $line.MarkerSize=11
    foreach($r in $rows) {
        $i=$line.Points.AddXY([double]$r.capacity_percent,[double]$r.accuracy_delta_pp)
        $p=$line.Points[$i]
        $p.MarkerColor=if($r.all_three_pass -eq 'true'){[Drawing.Color]::ForestGreen}else{[Drawing.Color]::Firebrick}
        $p.Label="$($r.label)%"
        if($r.frozen -eq 'true'){$p.Label+=' frozen NO-GO'}
        if($r.selected -eq 'true'){$p.Label+=' selected'}
        $p.LabelForeColor=[Drawing.Color]::Black
    }
    $chart.Series.Add($line)
    $floor=New-Object System.Windows.Forms.DataVisualization.Charting.Series('Registered accuracy floor (-2 pp)')
    $floor.ChartType=[System.Windows.Forms.DataVisualization.Charting.SeriesChartType]::Line
    $floor.Color=[Drawing.Color]::Firebrick
    $floor.BorderDashStyle=[System.Windows.Forms.DataVisualization.Charting.ChartDashStyle]::Dash
    $floor.BorderWidth=2
    $null=$floor.Points.AddXY(0,-2)
    $null=$floor.Points.AddXY(45,-2)
    $chart.Series.Add($floor)
    $title=$chart.Titles.Add('Distilled ROI capacity curve: fixed FP32 teacher, seed 0')
    $title.Font=New-Object Drawing.Font('Arial',17,[Drawing.FontStyle]::Bold)
    $note=$chart.Titles.Add('Validation n=12; development selection only; no independent judgement. No interpolation or confidence claim.')
    $note.Font=New-Object Drawing.Font('Arial',10)
    $note.Docking=[System.Windows.Forms.DataVisualization.Charting.Docking]::Bottom
    $chart.SaveImage([IO.Path]::GetFullPath($OutputPng),[System.Windows.Forms.DataVisualization.Charting.ChartImageFormat]::Png)
} finally {
    $chart.Dispose()
}
