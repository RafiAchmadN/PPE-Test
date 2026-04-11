// import "./bootstrap";

function deployModal(row_id) {
    var modal = document.getElementById("modal" + row_id);

    // Get the image and insert it inside the modal - use its "alt" text as a caption
    var img = document.getElementById(row_id);
    var modalImg = document.getElementById("image" + row_id);
    modal.style.display = "block";
    modalImg.src = img.src;

    var span = document.getElementById("close" + row_id);

    // When the user clicks on <span> (x), close the modal
    span.onclick = function () {
        modal.style.display = "none";
    };
}

