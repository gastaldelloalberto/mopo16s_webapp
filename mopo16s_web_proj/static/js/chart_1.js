window.scoreIndexes = [2, 3, 4];
let labels = ["Efficiency", "Coverage", "Matching-bias"];


function renderChart() {
    let data_init;
    let data_out;
    // reapply mapping
    if (window.scoreIndexes[0] === 2 && window.scoreIndexes[1] === 3) {
        if (window.matchingbias === undefined) {
            window.matchingbias = {
                data_init: window.result.init.map(parseElement),
                data_out: window.result.out.map(parseElement)
            };
        }
        data_init = window.matchingbias.data_init;
        data_out = window.matchingbias.data_out;
    } else if (window.scoreIndexes[0] === 2 && window.scoreIndexes[1] === 4) {
        if (window.coverage === undefined) {
            window.coverage = {
                data_init: window.result.init.map(parseElement),
                data_out: window.result.out.map(parseElement)
            };
        }
        data_init = window.coverage.data_init;
        data_out = window.coverage.data_out;
    } else {
        if (window.efficiency === undefined) {
            window.efficiency = {
                data_init: window.result.init.map(parseElement),
                data_out: window.result.out.map(parseElement)
            };
        }
        data_init = window.efficiency.data_init;
        data_out = window.efficiency.data_out;
    }


    // let data_init = window.result.init.map(parseElement);
    // let data_out = window.result.out.map(parseElement);
    let data = {
        datasets: [
            {
                "label": "Initial primer pairs",
                "data": data_init,
                "backgroundColor": "rgba(0,0,255,0.2)",
                "pointBackgroundColor": "rgba(0,0,255,0.5)",
                "borderColor": "rgba(0,0,255,0.5)",
                "pointBorderColor": "rgba(0,0,255,1)",
                "pointStrokeColor": "rgba(0,0,255,1)",
            },
            {
                "label": "Optimized primer pairs",
                "data": data_out,
                "backgroundColor": "rgba(0,255,0,0.2)",
                "pointBackgroundColor": "rgba(0,255,0,0.5)",
                "borderColor": "rgba(0,255,0,0.5)",
                "pointBorderColor": "rgba(0,255,0,1)",
                "pointStrokeColor": "rgba(0,255,0,1)",
            },
        ],
    };
    let options = {
        tooltips: {
            "callbacks": {
                "label": (tooltipItem, data) => {
                    return data.datasets[tooltipItem.datasetIndex].data[tooltipItem.index].label;
                }
            }
        },
        scales: {
            xAxes: [{
                scaleLabel: {
                    display: true,
                    labelString: labels[window.scoreIndexes[0] - 2]// "-2" because in "labels" there are only the 3 sccores
                },
                ticks: {
                    reverse: window.scoreIndexes[0] === 4,//reverse only matching-bias
                }

            }],
            yAxes: [{
                scaleLabel: {
                    display: true,
                    labelString: labels[window.scoreIndexes[1] - 2]// "-2" because in "labels" there are only the 3 sccores
                },
                ticks: {
                    reverse: window.scoreIndexes[1] === 4,//reverse only matching-bias
                }
            }]
        }
    };
    if (window.myGraph !== undefined) {
        window.myGraph.data = data;
        window.myGraph.options = options;
        window.myGraph.update();
    } else {
        const ctx = document.getElementById("chart_1").getContext('2d');
        window.myGraph = new Chart(ctx, {
                type: 'bubble',
                data: data,
                options: options,
            }
        );
    }
    // window.chart_base64=window.myGraph.toDataURL('image/jpg')
}

window.addEventListener("DOMContentLoaded", function () {
    // process init
    let result = window.result
    let min = 10, max = 0;
    for (let j = 2; j < 5; j++) {
        for (let i = 0; i < result.init.length; i++) {
            let item = result.init[i][j];
            if (item < min) min = item;
            if (item > max) max = item;
        }
        max = max - min;
        for (let i = 0; i < result.init.length; i++) {
            if (j === 4) {
                result.init[i].push(14 - (result.init[i][j] - min) * 9 / max);
            } else {
                result.init[i].push((result.init[i][j] - min) * 9 / max + 5);
            }
        }
        // normalize out
        min = 10;
        max = 0;
        for (let i = 0; i < result.out.length; i++) {
            let item = result.out[i][j];
            if (item < min) min = item;
            if (item > max) max = item;
        }
        max = max - min;
        for (let i = 0; i < result.out.length; i++) {
            if (j === 4) {
                result.out[i].push(14 - (result.out[i][j] - min) * 9 / max);
            } else {
                result.out[i].push((result.out[i][j] - min) * 9 / max + 5);
            }
        }
    }
    window.result = result;
    renderChart();
});

function parseElement(elem) {
    return {
        x: elem[window.scoreIndexes[0]],
        y: elem[window.scoreIndexes[1]],
        r: elem[window.scoreIndexes[2] + 3],
        // r: elem[5] * 3,
        label: [
            "Forward primers: " + elem[0].join('  '),
            "Reverse primers: " + elem[1].join('  '),
            "Efficiency: " + elem[2],
            "Coverage: " + elem[3],
            "Matching-bias: " + elem[4],
        ],
    }
}
