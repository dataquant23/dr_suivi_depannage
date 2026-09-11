/**
 * Compression des photos avant envoi : le reseau terrain est souvent faible,
 * on reduit la taille des images cote telephone avant de les inclure dans le
 * formulaire. A l affichage, ce sont des JPEG normaux : aucune decompression
 * particuliere n est necessaire, le navigateur les affiche nativement.
 */

/**
 * Compresse une image (redimensionnement + reencodage JPEG). Renvoie le
 * fichier original si la compression echoue ou n apporte aucun gain (ex :
 * petite image deja compacte).
 */
async function compresserImage(fichier, maxDimension = 1600, qualite = 0.75) {
  if (!fichier.type || !fichier.type.startsWith("image/") || fichier.type === "image/svg+xml") {
    return fichier;
  }
  try {
    const bitmap = await createImageBitmap(fichier);
    let {width, height} = bitmap;
    if (width > maxDimension || height > maxDimension) {
      const ratio = Math.min(maxDimension / width, maxDimension / height);
      width = Math.round(width * ratio);
      height = Math.round(height * ratio);
    }

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    canvas.getContext("2d").drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", qualite));
    if (!blob || blob.size >= fichier.size) return fichier;

    const nom = fichier.name.replace(/\.[^.]+$/, "") + ".jpg";
    return new File([blob], nom, {type: "image/jpeg", lastModified: Date.now()});
  } catch (erreur) {
    return fichier;
  }
}

/** Compresse chaque fichier d une FileList/tableau, en serie. */
async function compresserFichiers(fichiers) {
  const resultats = [];
  for (const fichier of fichiers) resultats.push(await compresserImage(fichier));
  return resultats;
}

/**
 * Remplace le contenu d un <input type="file"> par ses versions compressees.
 * Le champ "capture"/"multiple" de l input est preserve, seul le contenu
 * (FileList) change, via l API DataTransfer.
 */
async function compresserEtRemplacer(input) {
  const compresses = await compresserFichiers([...input.files]);
  const transfert = new DataTransfer();
  compresses.forEach((f) => transfert.items.add(f));
  input.files = transfert.files;
}
