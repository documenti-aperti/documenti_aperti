'use strict';

var hocrProofreader;
var hocrBaseUrl;
var hocrUrl;
var args = {};

Util.onReady(function () {
    hocrProofreader = new HocrProofreader({
        layoutContainer: 'layout-container',
        editorContainer: 'editor-container'
    });


    location.search.substr(1).split("&").forEach(function(arg){
    	var temp = arg.split("=");
		args[decodeURI(temp[0])] = decodeURI(temp[1]);
    });

    document.getElementById('toggle-layout-image').addEventListener('click', function () {
        hocrProofreader.toggleLayoutImage();
    });

    document.getElementById('zoom-page-full').addEventListener('click', function () {
        hocrProofreader.setZoom('page-full');
    });

    document.getElementById('zoom-page-width').addEventListener('click', function () {
        hocrProofreader.setZoom('page-width');
    });

    document.getElementById('zoom-original').addEventListener('click', function () {
        hocrProofreader.setZoom('original');
    });

    document.getElementById('button-save').addEventListener('click', function () {
        document.getElementsByName('user')[0].value = args["user_id"];
        document.getElementsByName('idProject')[0].value = args["repo_id"];
        document.getElementsByName('hocrData')[0].value = hocrProofreader.getHocr();
    });

    hocrBaseUrl = 'https://documentiaperti.org/'+args["user_name"]+'/'+args["repo_name"]+'/raw/branch/master/images/';
    hocrUrl = 'https://documentiaperti.org/'+args["user_name"]+'/'+args["repo_name"]+'/raw/branch/master/hocr/'+args["repo_name"]+'.hocr';

    if (!("user_id" in args)) {
        document.getElementById('button-save').style.display = "none";
    }

    document.getElementById('button-export').download = args["repo_name"]+".hocr";

    Util.get(hocrUrl, function (err, hocr) {
        if (err) return Util.handleError(err);

        hocrProofreader.setHocr(hocr, hocrBaseUrl);
    });

    hocrProofreader.setZoom('zoom-page-full');

    window.onhashchange = function() {
        console.log("MSMSMSMS");
    }
});

function getCookie(nome) {
    var name = nome + "=";
    var ca = document.cookie.split(';');
    for (var i = 0; i < ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ')
            c = c.substring(1);
        if (c.indexOf(name) == 0) return c.substring(name.length, c.length);
    }
    return "";
}

function fileChanged() {
    var files = document.getElementById("button-upload").files;
    if (files.length == 0) {
        alert('Seleziona un file!');
        return;
    }
    var file = files[0];
    if (file.name.split(".")[1] != "hocr") {
        alert('Il file importato non è un file .hocr!');
        return;
    }
    var fileReader = new FileReader();
    fileReader.onload = function(fileLoadedEvent){
      var hocr = fileLoadedEvent.target.result;
      hocrProofreader.setHocr(hocr,hocrBaseUrl);
    };

    fileReader.readAsText(file, "UTF-8");
}

function setDownload(element){
    element.href="data:application/octet-stream;charset=utf-8;base64,"+btoa("<html>"+unescape(encodeURIComponent(hocrProofreader.getHocr()))+"</html>");
}

window.onpopstate = function() {
    window.location = "https://documentiaperti.org/"+args["user_name"]+"/"+args["repo_name"];
}