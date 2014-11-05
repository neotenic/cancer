mongoose = require 'mongoose'
cheerio = require 'cheerio'
request = require 'request'
async   = require 'async'
unzip   = require 'unzip'
libpath = require 'path'
fs      = require 'fs.extra'
cp      = require 'child_process'
_       = require 'underscore'
unoconv = require 'unoconv'

config = (try JSON.parse(fs.readFileSync('config.json'))) || {}

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
	engine:           String,
	error:            String,
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


convert = (options, inputfile, callback) ->
	apirequest = request.post({
		url: "https://api.cloudconvert.org/convert"
		followAllRedirects: true
		qs: options
	}, (error, response, body) ->
		if response.statusCode is 200
			callback(null, body)
		else
			callback new Error(JSON.parse(body).error)
	)
	apirequest.form().append "file", fs.createReadStream(inputfile)  if inputfile


process_packet_cc = ->
	key_index = 0
	Packet.findOne { html: null }, (err, packet) ->
		ext = libpath.extname(packet.name)
		if /^expand/.test(packet.href)
			throw 'walp expansions'



		if ext == '.docx'
			options.inputformat = 'docx'
		else if ext == '.pdf'
			options.inputformat = 'pdf'
		else
			throw 'oh shit unsupported format' + ext
		
		console.log packet.name, ext

		convert options, null, (err, html) ->
			return console.log 'error', err if err
			packet.html = html
			packet.engine = 'cloudconvert'
			packet.save()
			console.log 'done and saved', html
			process_packet()

convert_cloud = (tempname, cb) ->
	key_index = 0
	options =
		apikey: config.cloudconvert[key_index]
		input: "upload"
		download: "inline"
		outputformat: "html"
		inputformat: libpath.extname(tempname).slice(1)
	convert options, tempname, cb

convert_calibre = (tempname, cb) ->
	outname  = "temp/output-calibre-#{temp_counter++}"
	proc = cp.spawn('/Applications/calibre.app/Contents/MacOS/ebook-convert', [tempname, outname, '-vvvv'])
	console.log [tempname, outname]
	proc.on 'close', (code, signal) ->
		console.log 'process is finished', code, signal
		fs.readFile outname + "/index.html", 'utf8', (err, html) ->
			fs.rmrf outname, ->
				cb err, html
	proc.stdout.on 'data', (data) ->
		console.log 'data', data.toString()
	proc.stderr.on 'data', (data) ->
		console.log 'stderr', data.toString()
	console.log 'done with', tempname

convert_unoconv = (tempname, cb) ->
	unoconv.convert tempname, 'html', {
		bin: 'unoconv/unoconv'
	}, (err, data) ->
		return cb err if err
		cb err, data.toString()

convert_plaintext = (tempname, cb) ->
	fs.readFile tempname, 'utf8', cb

temp_counter = 0

process_packet = (packet, complete) ->
	console.log packet
	ext = libpath.extname(packet.name).toLowerCase()

	tempname = "temp/input-#{temp_counter++}#{ext}"
	
	done_conversion = (err, html) ->
		return complete err, html if err
		packet.html = html
		packet.save ->
			console.log 'done conversion, saved and whatevs'
			fs.unlink tempname, -> complete null, html

	start_conversion = ->
		if ext in ['.pdf'] and false
			packet.engine = 'cloudconvert'
			convert_cloud tempname, done_conversion
		else if ext in ['.pdf']
			packet.engine = 'calibre'
			convert_calibre tempname, done_conversion
		else if ext in ['.doc', '.docx', '.rtf', '.wpd']
			packet.engine = 'unoconv'
			convert_unoconv tempname, done_conversion
		else if ext in ['.txt']
			packet.engine = 'plaintext'
			convert_plaintext tempname, done_conversion
		
		else
			packet.error = 'unsupported document type'
			packet.save ->
				complete null

	if /^expand/.test(packet.href)
		source = fs.createReadStream(packet.href)
	else
		source = request(packet.href)

	source
		.pipe(fs.createWriteStream(tempname))
		.on 'close', start_conversion


# Packet.findOne { html: null, name: {$regex: /pdf/i} }, (err, packet) ->
# process_packet()
next_group = ->
	Packet.find({ html: null, error: null }).limit(320).exec (err, packets) ->
		async.eachLimit packets, 1, process_packet, (err) ->
			console.log 'done with each (document) for 20', err
			next_group()

next_group()

# next_group_unoconv = ->
# 	Packet.find({ html: null, error: null, name: {$regex: /\.(doc|docx|rtf)$/i } }).limit(20).exec (err, packets) ->
# 		async.eachLimit packets, 1, process_packet, (err) ->
# 			console.log 'done with each (document) for 20', err
# 			next_group_unoconv()

# next_group_calibre = ->
# 	Packet.find({ html: null, error: null, name: {$regex: /\.pdf$/i } }).limit(20).exec (err, packets) ->
# 		async.eachLimit packets, 3, process_packet, (err) ->
# 			console.log 'done with each (pdf) for 20', err
# 			next_group_calibre()


# next_group_unoconv()
# next_group_calibre()


