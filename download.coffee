mongoose = require 'mongoose'
cheerio = require 'cheerio'
request = require 'request'
async   = require 'async'
unzip   = require 'unzip'
libpath = require 'path'
fs      = require 'fs'
_       = require 'underscore'

db = mongoose.createConnection 'localhost', 'cancer'
db.on 'error', (err) -> console.log 'database error', err
db.on 'open', (err) -> console.log 'opened database'


Question = db.model 'Question', new mongoose.Schema {
	type:             String, # for future support for different types of Question, e.g. certamen, jeopardy
	category:         String,
	num:              Number,
	tournament:       String,
	question:         String,
	answer:           String,
	difficulty:       String,
	value:            String,
	date:             String,
	year:             Number,
	round:            String,
	seen:             Number, 
	next:             mongoose.Schema.ObjectId,
	fixed:            Number,
	inc_random:       Number,
	tags:             [String]
}


Packet = db.model 'Packet', new mongoose.Schema {
	href:             String,
	name:             String,
	html:             String,
	tournament:       mongoose.Schema.ObjectId
}

Tournament = db.model 'Tournament', new mongoose.Schema {
	difficulty:       String,
	year:             Number,
	source:           String,
	owner:            String,
	season:           String,
	links:            [String],
	name:             String
}

get_tournaments = (path, cb) ->
	request path, (err, res, body) ->
		$ = cheerio.load(body)
		tournaments = for e in $('.MainColumn ul>li>span.Name>a').get()
			{ href: path + $(e).attr('href'), name: $(e).text() }
		cb? null, tournaments


tournament_info = (path, cb) ->
	request path, (err, res, body) ->
		# { 'Target level': 'College', 'Season primarily used': '2014-2015' }
		$ = cheerio.load(body)
		name = $('.MainColumn .First h2').text().trim()
		links = ($(e).attr('href') for e in $('#ActionBox a').get())
		fields = _.object (for field in $('.MainColumn p>span.FieldName').get()
			[ $(field).text().replace(':', '').trim(), $(field).parent().text().replace($(field).text(), '').trim() ])

		files = for link in $('ul.FileList>li>a').get()
			{ href: $(link).attr('href'), name: $(link).text() }

		owner = $('.PermissionsInformation').text()
		cb? { name, fields, files, links, owner }


zipCounter = 0
cached_lookup = (path, cb) ->
	Tournament.count { source: path }, (err, count) ->
		console.log path, count
		if count > 0
			cb?() # we're done here, it already exists, go on
		else
			tournament_info path, ({name, fields, files, links, owner}) ->
				console.log 'creating tournament', name
				year = name.match(/^\d{4}/) || fields['Season primarily used']?.split('-')?[0]

				t = new Tournament {
					source: path
					difficulty: fields['Target level']
					season: fields['Season primarily used']
					year: (if year then parseInt(year) else null)
					links
					name
					owner
				}
				zips = _.pluck(files, 'name').filter (x) -> /\.zip$/i.test(x)
				if files.length == 1 and zips.length == 1
					
					request(files[0].href)
						.pipe(unzip.Parse())
						.on('close', -> 
							console.log 'finished with tournament', t.name
						)
						.on('error', (err) -> console.log 'zip decode error', err)
						.on 'entry', (entry) ->
							{ path, type, size } = entry
							
							if type == 'File' and !/__MACOSX|\.DS_STORE|\.git|\/./.test(path)
								console.log path, t.name
								filename = 'expand/Z' + (++zipCounter) + '-' + libpath.basename(path)
								entry.pipe(fs.createWriteStream(filename))
								
								p = new Packet {
									tournament: t
									href: filename
									name: libpath.basename(filename)
								}
								p.save ->
							else
								entry.autodrain()
					t.save cb
				else
					async.map files, (({href, name}, fin) ->
						if !/\.zip$/i.test(name)
							p = new Packet {
								tournament: t
								href
								name
							}
							p.save fin
						else
							fin()
					), (err, packets) ->
						t.save cb

sources = [
	'http://collegiate.quizbowlpackets.com/',
	'http://www.quizbowlpackets.com/'
]


# async.map sources, get_tournaments, (err, data) ->
# 	tournament_paths = _.shuffle(_.pluck(_.flatten(data), 'href'))
# 	async.eachLimit tournament_paths, 1, cached_lookup, (err) ->
# 		if err
# 			console.log 'error exploring tournaments', err
# 		else
# 			console.log 'done with exploring tournaments'


console.log Packet.findOne()


convert_packet()
