newsflow = {}

newsflow.do_search = function(q) {
	group = $('#groups').val();

	$.getJSON('/api/1/' + group + '/search.json', {q: q}, function(data) {
		$('#content .nzb').remove();
		$('#content .rss').html('<a href="/api/1/' + group + '/search.rss?q=' + q + '"><img src="/img/icons/rss.png" alt="RSS" /></a>').show();
		for(i = 0; i < data.length; i++) {
			ts = new Date();
			ts.setTime(data[i].ts * 1000);
			$('#content').append('<li class="nzb"><a href="/api/1/' + group + '/nzb/' + data[i].name + '">' + data[i].name + '</a><div class="easydate">' + ts + '</div></li>');
		}

		$('.easydate').easydate();
	});
}

newsflow.get_recent = function() {
    group = $('#groups').val();

    $.getJSON('/api/1/' + group + '/recent.json', function(data) {
        $('#content .nzb').remove();
		$('#content .rss').html('<a href="/api/1/' + group + '/recent.rss"><img src="/img/icons/rss.png" alt="RSS" /></a>').show();
        for(i = 0; i < data.length; i++) {
            ts = new Date();
            ts.setTime(data[i].ts * 1000);
            $('#content').append('<li class="nzb"><a href="/api/1/' + group + '/nzb/' + data[i].name + '">' + data[i].name + '</a><div class="easydate">' + ts + '</div></li>');
        }

        $('.easydate').easydate();
    });
}

newsflow.get_groups = function() {
	$.ajax({
		url: '/api/1/',
		dataType: 'json',
		async: false,
		success: function(data) {
			for(i = 0; i < data.length; i++) {
				$('#groups').append('<option value="' + data[i] + '">' + data[i] + '</option>');
			}
		}
	});
}

