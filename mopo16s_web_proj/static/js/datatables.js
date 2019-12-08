$(document).ready(function () {
    options = {
        pageLength: 50,
        select: true,
        dom: 'Bfrtip',
        buttons: ['copy', 'pdf', 'excel'],
    };
    let table_init = $('#T_table_init').DataTable(options);
    let table_out = $('#T_table_out').DataTable(options);
    new $.fn.dataTable.Buttons(table_init, {
        buttons: ['copy', 'pdf', 'excel']
    });
    new $.fn.dataTable.Buttons(table_out, {
        buttons: ['copy', 'pdf', 'excel']
    });
});